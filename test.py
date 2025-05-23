import torch
from IPython.display import Image, display

# YOLOv5の事前学習済みモデルをロード
model = torch.hub.load('ultralytics/yolov5', 'yolov5s')

# 画像のパス
img_path = '/Users/dangararara/lecture/miraisouzou/images/001809.jpg'

# 画像から服の部分を検出
results = model(img_path)

# 検出された画像を保存
results.save()  # "runs/detect/exp/" フォルダに結果が保存されます

# 検出されたBounding Boxの情報を表示
detections = results.pandas().xyxy[0]
print(detections)