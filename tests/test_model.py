import pytest
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

@pytest.fixture(scope="module")
def model_and_tokenizer():
    """Fixture to load the model and tokenizer once for all tests."""
    model_name = "distilbert-base-uncased"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    return model, tokenizer

def test_transformer_model_output_cpu(model_and_tokenizer):
    """Tests the model output on a CPU."""
    model, tokenizer = model_and_tokenizer
    text = "Hugging Face makes NLP easy."
    inputs = tokenizer(text, return_tensors="pt")
    outputs = model(**inputs)
    # Default distilbert-base-uncased for sequence classification has 2 labels
    assert outputs.logits.shape == (1, 2)

@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="MPS not available on this machine")
def test_transformer_model_output_mps(model_and_tokenizer):
    """Tests the model output on Apple's MPS hardware, if available."""
    model, tokenizer = model_and_tokenizer
    device = torch.device("mps")
    model.to(device)
    text = "Hugging Face makes NLP easy."
    inputs = tokenizer(text, return_tensors="pt").to(device)
    outputs = model(**inputs)
    assert outputs.logits.shape == (1, 2)