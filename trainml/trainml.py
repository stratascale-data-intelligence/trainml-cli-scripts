import json
import os
import asyncio
import aiohttp
from importlib.metadata import version

from trainml.auth import Auth
from trainml.datasets import Datasets
from trainml.models import Models
from trainml.jobs import Jobs
from trainml.gpu_types import GpuTypes
from trainml.environments import Environments
from trainml.exceptions import ApiError, TrainMLException
from trainml.connections import Connections
from trainml.projects import Projects


async def ws_heartbeat(ws):
    while not ws.closed:
        try:
            await ws.send_json(
                dict(
                    action="heartbeat",
                )
            )
        except:
            await ws.close()
            break
        await asyncio.sleep(9 * 60)


class TrainML(object):
    def __init__(self, **kwargs):
        self._version = version("trainml")
        CONFIG_DIR = os.path.expanduser(
            os.environ.get("TRAINML_CONFIG_DIR") or "~/.trainml"
        )
        try:
            with open(f"{CONFIG_DIR}/environment.json", "r") as file:
                env_str = file.read().replace("\n", "")
            env = json.loads(env_str)
        except OSError:
            env = dict()
        try:
            with open(f"{CONFIG_DIR}/config.json", "r") as file:
                config_str = file.read().replace("\n", "")
            config = json.loads(config_str)
        except OSError:
            config = dict()
        self.domain_suffix = (
            kwargs.get("domain_suffix")
            or os.environ.get("TRAINML_DOMAIN_SUFFIX")
            or env.get("domain_suffix")
            or "trainml.ai"
        )
        self.auth = Auth(
            user=kwargs.get("user"),
            key=kwargs.get("key"),
            region=kwargs.get("region"),
            client_id=kwargs.get("client_id"),
            pool_id=kwargs.get("pool_id"),
        )
        self.active_project = (
            kwargs.get("project")
            or os.environ.get("TRAINML_PROJECT")
            or config.get("project")
        )
        self.datasets = Datasets(self)
        self.models = Models(self)
        self.jobs = Jobs(self)
        self.gpu_types = GpuTypes(self)
        self.environments = Environments(self)
        self.connections = Connections(self)
        self.projects = Projects(self)
        self.api_url = (
            kwargs.get("api_url")
            or os.environ.get("TRAINML_API_URL")
            or env.get("api_url")
            or "api.trainml.ai"
        )
        self.ws_url = (
            kwargs.get("ws_url")
            or os.environ.get("TRAINML_WS_URL")
            or env.get("ws_url")
            or "api-ws.trainml.ai"
        )

    async def _query(self, path, method, params=None, data=None, headers=None):
        try:
            tokens = self.auth.get_tokens()
        except Exception:
            raise TrainMLException(
                "Error getting authorization tokens.  Verify configured credentials."
            )
        headers = (
            {
                **headers,
                **{
                    "Authorization": tokens.get("id_token"),
                    "User-Agent": f"trainML-sdk/{self._version}",
                },
            }
            if headers
            else {
                "Authorization": tokens.get("id_token"),
                "User-Agent": f"trainML-sdk/{self._version}",
            }
        )
        if self.active_project:
            params = (
                {**params, **{"project_uuid": self.active_project}}
                if params
                else {"project_uuid": self.active_project}
            )

        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        url = f"https://{self.api_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                data=json.dumps(data),
                headers=headers,
                params=params,
            ) as resp:
                if (resp.status // 100) in [4, 5]:
                    what = await resp.read()
                    content_type = resp.headers.get("content-type", "")
                    resp.close()
                    if content_type == "application/json":
                        raise ApiError(
                            resp.status, json.loads(what.decode("utf8"))
                        )
                    else:
                        raise ApiError(
                            resp.status, {"message": what.decode("utf8")}
                        )
                results = await resp.json()
                return results

    async def _ws_subscribe(self, entity, id, msg_handler):
        tokens = self.auth.get_tokens()
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                f"wss://{self.ws_url}?Authorization={tokens.get('id_token')}"
            ) as ws:
                asyncio.create_task(
                    ws.send_json(
                        dict(
                            action="getlogs",
                            data=dict(
                                type="init",
                                entity=entity,
                                id=id,
                                project_uuid=self.active_project,
                            ),
                        )
                    )
                )
                asyncio.create_task(
                    ws.send_json(
                        dict(
                            action="subscribe",
                            data=dict(
                                type="logs",
                                entity=entity,
                                id=id,
                                project_uuid=self.active_project,
                            ),
                        )
                    )
                )
                asyncio.create_task(ws_heartbeat(ws))
                async for msg in ws:
                    if msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                        aiohttp.WSMsgType.CLOSE,
                    ):
                        await ws.close()
                        break
                    msg_handler(msg)

    def set_active_project(self, project_uuid):
        CONFIG_DIR = os.path.expanduser(
            os.environ.get("TRAINML_CONFIG_DIR") or "~/.trainml"
        )
        with open(f"{CONFIG_DIR}/config.json", "w") as file:
            json.dump(dict(project=project_uuid), file)
