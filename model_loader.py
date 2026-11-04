import torch
import torch.nn as nn
from torchvision.models import mobilenet_v3_small


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

NUM_CLASSES = 31
MODEL_PATH = "model/mobilenet_v3_small_best.pth"

DEVICE = torch.device("cpu")


# --------------------------------------------------
# CREATE MODEL
# --------------------------------------------------

model = mobilenet_v3_small(weights=None)

# Replace the classifier with the same 31-class output
in_features = model.classifier[-1].in_features

model.classifier[-1] = nn.Linear(
    in_features,
    NUM_CLASSES
)


# --------------------------------------------------
# LOAD TRAINED CHECKPOINT
# --------------------------------------------------

checkpoint = torch.load(
    MODEL_PATH,
    map_location=DEVICE
)


# Handle different checkpoint formats
if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
    model.load_state_dict(checkpoint["model_state_dict"])
else:
    model.load_state_dict(checkpoint)


# --------------------------------------------------
# EVALUATION MODE
# --------------------------------------------------

model = model.to(DEVICE)
model.eval()


print("=" * 60)
print("MOBILENETV3 MODEL LOADED")
print("=" * 60)
print("Model: MobileNetV3-Small")
print("Classes:", NUM_CLASSES)
print("Device:", DEVICE)
print("Checkpoint:", MODEL_PATH)
print("Status: READY")
print("=" * 60)