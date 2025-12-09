from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

model_name = "distilbert-base-uncased"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)

text = "Hugging Face makes NLP easy."

inputs = tokenizer(text, return_tensors="pt")
outputs = model(**inputs)

print(outputs.logits)

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
model.to(device)

inputs = tokenizer(text, return_tensors="pt").to(device)
outputs = model(**inputs)
