import trainml
import asyncio


trainml = trainml.TrainML()

dataset = asyncio.run(
    trainml.datasets.create(
        name="Test CLI Dataset",
        source_type="aws",
        source_uri="s3://trainml-examples/data/cifar10",
        wait=True,
    )
)

print(dataset)

job = asyncio.run(
    trainml.jobs.create(
        name="Test CLI Training Job",
        type="headless",
        gpu_type_name="RTX 2070 Super",
        gpu_count=1,
        disk_size=10,
        worker_count=1,
        worker_commands=[
            "PYTHONPATH=$PYTHONPATH:$TRAINML_MODEL_PATH python -m official.vision.image_classification.resnet_cifar_main --num_gpus=1 --data_dir=$TRAINML_DATA_PATH --model_dir=$TRAINML_OUTPUT_PATH --enable_checkpoint_and_export=True --train_epochs=10 --batch_size=1024",
        ],
        data=dict(
            datasets=[dict(id=dataset.id, type="existing")],
            output_uri="s3://trainml-examples/output/resnet_cifar10",
            output_type="aws",
        ),
        model=dict(git_uri="git@github.com:trainML/test-private.git"),
        wait=True,
    )
)

print(job)