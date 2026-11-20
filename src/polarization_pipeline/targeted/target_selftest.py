"""Small real-torch checks before any target-aware GPU fit; no corpus or downloads."""
def verify_target_models():
    import tempfile
    from pathlib import Path
    import torch
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizer, AutoTokenizer
    from .target_model import TargetMaxBertForSequenceClassification
    from .targetaware import MARKERS, REPRESENTATIONS, load_classifier, marked_encoding, marked_example, representation

    with tempfile.TemporaryDirectory(prefix="target-aware-check-") as directory:
        root = Path(directory)
        vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "apoyo", "a", "ana", "pero", "rechazo", "luis", ".", "san", "##chez", "sanchez"]
        (root / "vocab.txt").write_text("\n".join(vocab) + "\n")
        text = "Apoyo a Ana pero rechazo a Luis."
        rows = [{"text": text, "target_name": name, "mention_start": text.index(name), "mention_end": text.index(name) + len(name)} for name in ["Ana", "Luis"]]
        torch.manual_seed(123)
        for value in REPRESENTATIONS:
            tokenizer = BertTokenizer(vocab_file=str(root / "vocab.txt"), do_lower_case=True)
            tokenizer.add_special_tokens({"additional_special_tokens": list(MARKERS)})
            tokenizer.init_kwargs["target_representation"] = value
            config = BertConfig(vocab_size=len(tokenizer), hidden_size=16, num_hidden_layers=1,
                                num_attention_heads=2, intermediate_size=32, num_labels=5, max_position_embeddings=64,
                                target_representation=value, classifier_dropout=0.1)
            model = (TargetMaxBertForSequenceClassification(config) if value == "marked_target_max" else BertForSequenceClassification(config)).eval()
            inputs = marked_encoding(tokenizer, rows, 64)
            with torch.no_grad():
                output = model(**inputs).logits
                individual = torch.cat([model(**marked_encoding(tokenizer, [row], 64)).logits for row in rows])
            if not torch.allclose(output, individual, atol=1e-6, rtol=1e-5):
                raise RuntimeError("Predicción por lotes inconsistente")
            destination = root / value
            model.save_pretrained(destination); tokenizer.save_pretrained(destination)
            restored_tokenizer = AutoTokenizer.from_pretrained(destination, use_fast=False)
            restored_model = load_classifier(destination).eval()
            if representation(restored_tokenizer) != value:
                raise RuntimeError("Representación perdida al guardar tokenizador")
            with torch.no_grad():
                restored = restored_model(**marked_encoding(restored_tokenizer, rows, 64)).logits
            if not torch.equal(output, restored):
                raise RuntimeError("Checkpoint marcado no reproduce predicciones")
            masks = [marked_example(tokenizer, row)["target_mask"] for row in rows]
            if masks[0] == masks[1]:
                raise RuntimeError("Cambiar objetivo no cambia la máscara")
            if value == "marked_target_max":
                restored_model.train()
                loss = restored_model(**marked_encoding(restored_tokenizer, rows, 64)).logits.sum()
                loss.backward()
                if restored_model.classifier.weight.grad is None or not torch.isfinite(restored_model.classifier.weight.grad).all():
                    raise RuntimeError("Gradientes del clasificador dirigido inválidos")
    print("TARGET_AWARE_MODELS_VERIFIED", flush=True)
