#!/usr/bin/env python
"""モデルロードのテスト"""
import os
import sys

print("ステップ1: 環境変数設定")
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

print("ステップ2: torchインポート")
import torch
print(f"  PyTorch version: {torch.__version__}")

print("ステップ3: transformersインポート")
from transformers import BertJapaneseTokenizer, BertModel
import transformers
print(f"  Transformers version: {transformers.__version__}")

print("ステップ4: デバイス設定")
DEVICE = 'cpu'
print(f"  Device: {DEVICE}")

print("ステップ5: トークナイザーロード")
MODEL_NAME = 'cl-tohoku/bert-base-japanese-v3'
try:
    tokenizer = BertJapaneseTokenizer.from_pretrained(MODEL_NAME)
    print("  ✓ トークナイザーロード成功")
except Exception as e:
    print(f"  ❌ トークナイザーロード失敗: {e}")
    sys.exit(1)

print("ステップ6: モデルロード")
try:
    model = BertModel.from_pretrained(MODEL_NAME)
    print("  ✓ モデルロード成功")
except Exception as e:
    print(f"  ❌ モデルロード失敗: {e}")
    sys.exit(1)

print("ステップ7: モデルをCPUに移動")
try:
    model.to(DEVICE)
    model.eval()
    print("  ✓ モデル設定成功")
except Exception as e:
    print(f"  ❌ モデル設定失敗: {e}")
    sys.exit(1)

print("ステップ8: テスト推論")
try:
    test_text = "これはテストです"
    inputs = tokenizer(test_text, return_tensors='pt', max_length=512, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
    print(f"  ✓ テスト推論成功 (出力shape: {outputs.last_hidden_state.shape})")
except Exception as e:
    print(f"  ❌ テスト推論失敗: {e}")
    sys.exit(1)

print("\n✓ 全てのステップが成功しました！")
