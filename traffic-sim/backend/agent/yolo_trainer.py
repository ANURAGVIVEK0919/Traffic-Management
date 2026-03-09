# Import required modules
from ultralytics import YOLO
import os
import shutil

# Constants for training configuration
DATASET_YAML = 'data/driveindia/dataset.yaml'
PRETRAINED_WEIGHTS = 'yolov8n.pt'
OUTPUT_MODEL_PATH = 'models/yolo_traffic.pt'
EPOCHS = 50
IMAGE_SIZE = 640
BATCH_SIZE = 16


def train_yolo():
    # Load YOLO model with pretrained weights
    model = YOLO(PRETRAINED_WEIGHTS)
    # Fine-tune model on custom dataset
    model.train(
        data=DATASET_YAML,
        epochs=EPOCHS,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        project='models',
        name='yolo_traffic',
        exist_ok=True
    )
    # Copy best weights to output path
    shutil.copy('models/yolo_traffic/weights/best.pt', OUTPUT_MODEL_PATH)
    print(f"YOLO training complete. Model saved to {OUTPUT_MODEL_PATH}")
    return OUTPUT_MODEL_PATH


if __name__ == '__main__':
    train_yolo()
