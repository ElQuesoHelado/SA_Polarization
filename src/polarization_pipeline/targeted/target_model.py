"""BERT mention readout. Imported only in the optional torch environment."""
import torch
from transformers import BertModel, BertPreTrainedModel
from transformers.modeling_outputs import SequenceClassifierOutput


class TargetMaxBertForSequenceClassification(BertPreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        if config.target_representation != "marked_target_max":
            raise ValueError("Representación incompatible con target max")
        self.bert = BertModel(config, add_pooling_layer=False)
        self.dropout = torch.nn.Dropout(0.1)
        self.classifier = torch.nn.Linear(config.hidden_size, config.num_labels)
        self.post_init()

    def forward(self, input_ids=None, attention_mask=None, token_type_ids=None, target_mask=None, **kwargs):
        if (target_mask is None or target_mask.shape != input_ids.shape
                or not target_mask.bool().any(dim=1).all()):
            raise ValueError("Máscara de objetivo vacía o incompatible")
        selected = target_mask.bool()
        if ((selected & ~attention_mask.bool()).any()
                or (selected & token_type_ids.ne(1)).any()):
            raise ValueError("El objetivo debe pertenecer al comentario, sin padding")
        output = self.bert(input_ids=input_ids, attention_mask=attention_mask,
                           token_type_ids=token_type_ids, return_dict=True)
        hidden = output.last_hidden_state
        pooled = hidden.masked_fill(~selected.unsqueeze(-1), torch.finfo(hidden.dtype).min).amax(dim=1)
        return SequenceClassifierOutput(logits=self.classifier(self.dropout(pooled)))
