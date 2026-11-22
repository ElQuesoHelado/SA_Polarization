"""Real tiny encoder gradients and checkpoint reload; no pretrained weight download."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

AVAILABLE = bool(importlib.util.find_spec('torch') and importlib.util.find_spec('transformers'))


@unittest.skipUnless(AVAILABLE, 'Arquitecturas verificadas aparte con dependencias CPU/GPU')
class EncoderArchitectureTests(unittest.TestCase):
    def check_architecture(self, family):
        import torch
        from transformers import AutoModelForSequenceClassification, ModernBertConfig, DebertaV2Config
        from polarization_pipeline.targeted.targetaware import load_classifier
        from polarization_pipeline.targeted.common import LABELS
        torch.manual_seed(42)
        options = dict(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                       num_attention_heads=4, max_position_embeddings=512, num_labels=5,
                       id2label=dict(enumerate(LABELS)), label2id={v:i for i,v in enumerate(LABELS)})
        if family == 'modernbert':
            config = ModernBertConfig(**options, reference_compile=False, classifier_pooling='mean',
                                     bos_token_id=0, eos_token_id=2, pad_token_id=1, cls_token_id=0, sep_token_id=2,
                                     local_attention=16, global_attn_every_n_layers=2)
        else:
            config = DebertaV2Config(**options, relative_attention=True, position_buckets=16,
                                    max_relative_positions=32, pos_att_type=['p2c', 'c2p'], type_vocab_size=0)
        model = AutoModelForSequenceClassification.from_config(config)
        ids = torch.tensor([[3, 4, 5, 6, 7, 8], [3, 9, 6, 0, 0, 0]])
        mask = torch.tensor([[1, 1, 1, 1, 1, 1], [1, 1, 1, 0, 0, 0]])
        model.train()
        loss = model(input_ids=ids, attention_mask=mask, labels=torch.tensor([0, 1])).loss
        loss.backward()
        gradients = [p.grad for p in model.parameters() if p.grad is not None]
        self.assertTrue(gradients)
        self.assertTrue(all(torch.isfinite(g).all() for g in gradients))
        self.assertGreater(sum(g.abs().sum().item() for g in gradients), 0.)
        torch.optim.AdamW(model.parameters(), lr=2e-5).step()
        model.eval()
        with torch.no_grad():
            expected = model(input_ids=ids, attention_mask=mask).logits
            single = model(input_ids=ids[1:2, :3], attention_mask=mask[1:2, :3]).logits
        self.assertEqual(tuple(expected.shape), (2, 5))
        torch.testing.assert_close(expected[1:2], single, atol=1e-5, rtol=1e-4)
        with tempfile.TemporaryDirectory() as tmp:
            model.save_pretrained(tmp, safe_serialization=True)
            restored = load_classifier(Path(tmp)).eval()
            with torch.no_grad():
                actual = restored(input_ids=ids, attention_mask=mask).logits
            torch.testing.assert_close(actual, expected)
            self.assertEqual(restored.config.id2label, dict(enumerate(LABELS)))

    def test_modernbert_gradients_padding_and_reload(self):
        self.check_architecture('modernbert')

    def test_mdeberta_gradients_padding_and_reload(self):
        self.check_architecture('deberta-v2')
