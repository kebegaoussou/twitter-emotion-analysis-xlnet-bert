# -*- coding: utf-8 -*-
"""XLNet.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1G8tdbVxgZDIjobIAbWyRAexYbCgWPZaN
"""

import torch
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from transformers import XLNetTokenizer, XLNetForSequenceClassification
from transformers import BertTokenizer, BertForSequenceClassification
from transformers import GPT2Tokenizer, GPT2Model, GPT2PreTrainedModel
from transformers import AdamW
from tqdm import trange
import pandas as pd
import numpy as np
from torch.nn import BCEWithLogitsLoss
from sklearn.metrics import f1_score, recall_score, precision_score, classification_report
import logging
import argparse
from tqdm import tqdm
from torch import nn
from torch.nn import CrossEntropyLoss, MSELoss

from transformers.modeling_outputs import (
    BaseModelOutput,
    BaseModelOutputWithPooling,
    CausalLMOutput,
    MaskedLMOutput,
    MultipleChoiceModelOutput,
    NextSentencePredictorOutput,
    QuestionAnsweringModelOutput,
    SequenceClassifierOutput,
    TokenClassifierOutput,
)
logging.basicConfig(format = '%(asctime)s - %(levelname)s - %(name)s -   %(message)s',
                    datefmt = '%m/%d/%Y %H:%M:%S',
                    level = logging.INFO)
logger = logging.getLogger(__name__)

def metrics_frame(preds, labels, label_names):
    recall_micro = recall_score(labels, preds, average="micro")
    recall_macro = recall_score(labels, preds, average="macro")
    precision_micro = precision_score(labels, preds, average="micro")
    precision_macro = precision_score(labels, preds, average="macro")
    f1_micro = f1_score(labels, preds, average="micro")
    f1_macro = f1_score(labels, preds, average="macro")
    cr = classification_report(labels, preds, labels=list(range(len(label_names))), target_names=label_names)
    model_metrics = {"Precision, Micro": precision_micro, "Precision, Macro": precision_macro,
                     "Recall, Micro": recall_micro, "Recall, Macro": recall_macro,
                     "F1 score, Micro": f1_micro, "F1 score, Macro": f1_macro, "Classification report": cr}
    return model_metrics

class GPT2ForSequenceClassification(GPT2PreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        self.num_labels = config.num_labels

        self.gpt2 = GPT2Model(config)
        self.dropout = nn.Dropout(0.1)
        self.classifier = nn.Linear(config.hidden_size, config.num_labels)


        self.init_weights()
    def set_type(self, classification_type):
        self.classification_type = classification_type
    def forward(
            self, input_ids=None, attention_mask=None, token_type_ids=None,
            position_ids=None, head_mask=None, inputs_embeds=None, labels=None
    ):
        r"""
        labels (:obj:`torch.LongTensor` of shape :obj:`(batch_size,)`, `optional`):
            Labels for computing the sequence classification/regression loss.
            Indices should be in :obj:`[0, ..., config.num_labels - 1]`.
            If :obj:`config.num_labels == 1` a regression loss is computed (Mean-Square loss),
            If :obj:`config.num_labels > 1` a classification loss is computed (Cross-Entropy).
        """
        outputs = self.gpt2(
            input_ids
        )
        if self.classification_type == "last":
            pooled_output = outputs[0][:,-1,:]
        elif self.classification_type == "first":
            pooled_output = outputs[0][:,0,:]
        elif self.classification_type == "mean":
            pooled_output = torch.mean(outputs[0])
        elif self.classification_type == "max":
            pooled_output = torch.max(outputs[0])[0]
        elif self.classification_type == "min":
            pooled_output = torch.min(outputs[0])[0]
        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)

        loss = None
        if labels is not None:
            if self.num_labels == 1:
                #  We are doing regression
                loss_fct = MSELoss()
                loss = loss_fct(logits.view(-1), labels.view(-1))
            else:
                loss_fct = CrossEntropyLoss()
                loss = loss_fct(logits.view(-1, self.num_labels), labels.view(-1))

        output = (logits,)
        return ((loss,) + output) if loss is not None else output

class XLNetForMultiLabelSequenceClassification(XLNetForSequenceClassification):
    r"""
        Method overriding of XLNetForSequenceClassification to adapt it to multi-label classification
        Changes: labels vector is extended to the number labels instead of 1
    """

    def forward(self, input_ids, token_type_ids=None, input_mask=None, attention_mask=None,
                mems=None, perm_mask=None, target_mapping=None,
                labels=None, head_mask=None):
        transformer_outputs = self.transformer(input_ids, token_type_ids=token_type_ids,
                                               input_mask=input_mask, attention_mask=attention_mask,
                                               mems=mems, perm_mask=perm_mask, target_mapping=target_mapping,
                                               head_mask=head_mask)
        output = transformer_outputs[0]

        output = self.sequence_summary(output)
        logits = self.logits_proj(output)

        # Keep mems, hidden states, attentions if there are in it
        outputs = (logits,) + transformer_outputs[1:]

        if labels is not None:
            loss_fct = BCEWithLogitsLoss()
        #Changes: labels vector is extended to the number labels instead of 1
            loss = loss_fct(logits.view(-1, self.num_labels),
                            labels.view(-1, self.num_labels).type_as(logits.view(-1, self.num_labels)))
            outputs = (loss,) + outputs

        return outputs  # (loss), logits, (hidden_states), (attentions)

class GPT2ForMultiLabelSequenceClassification(GPT2PreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        self.num_labels = config.num_labels

        self.gpt2 = GPT2Model(config)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.classifier = nn.Linear(config.hidden_size, config.num_labels)

        self.init_weights()

    def forward(
            self, input_ids=None, attention_mask=None, token_type_ids=None,
            position_ids=None, head_mask=None, inputs_embeds=None, labels=None
    ):
        r"""
        labels (:obj:`torch.LongTensor` of shape :obj:`(batch_size,)`, `optional`):
            Labels for computing the sequence classification/regression loss.
            Indices should be in :obj:`[0, ..., config.num_labels - 1]`.
            If :obj:`config.num_labels == 1` a regression loss is computed (Mean-Square loss),
            If :obj:`config.num_labels > 1` a classification loss is computed (Cross-Entropy).
        """
        outputs = self.gpt2(
            input_ids
        )

        pooled_output = outputs[0][:-1:]
        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)
        outputs = (logits,)
        if labels is not None:
            loss_fct = BCEWithLogitsLoss()
        #Changes: labels vector is extended to the number labels instead of 1
            loss = loss_fct(logits.view(-1, self.num_labels),
                            labels.view(-1, self.num_labels).type_as(logits.view(-1, self.num_labels)))
            outputs = (loss,) + outputs

        return outputs  # (loss), logits, (hidden_states), (attentions)

class BertForMultiLabelSequenceClassification(BertForSequenceClassification):
    r"""
        Method overriding of BertForSequenceClassification to adapt it to multi-label classification
        Changes: labels vector is extended to the number labels instead of 1
    """

    def forward(self, input_ids=None, attention_mask=None, token_type_ids=None,
                position_ids=None, head_mask=None, inputs_embeds=None, labels=None):
        outputs = self.bert(input_ids,
                            attention_mask=attention_mask,
                            token_type_ids=token_type_ids,
                            position_ids=position_ids,
                            head_mask=head_mask)
        pooled_output = outputs[1]

        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)

        outputs = (logits,) + outputs[2:]  # add hidden states and attention if they are here

        if labels is not None:
            loss_fct = BCEWithLogitsLoss()
        #Changes: labels vector is extended to the number labels instead of 1
            loss = loss_fct(logits.view(-1, self.num_labels),
                            labels.view(-1, self.num_labels).type_as(logits.view(-1, self.num_labels)))
            outputs = (loss,) + outputs

        return outputs  # (loss), logits, (hidden_states), (attentions)


class InputExample(object):
    """A single training/test example for simple sequence classification."""

    def __init__(self, guid, text_a, text_b=None, labels=None):
        """Constructs a InputExample.

        Args:
            guid: Unique id for the example.
            text_a: string. The untokenized text of the first sequence. For single
            sequence tasks, only this sequence must be specified.
            text_b: (Optional) string. The untokenized text of the second sequence.
            Only must be specified for sequence pair tasks.
            label: (Optional) string. The label of the example. This should be
            specified for train and dev examples, but not for test examples.
        """
        self.guid = guid
        self.text_a = text_a
        self.text_b = text_b
        self.labels = labels


class InputFeatures(object):
    """A single set of features of data."""

    def __init__(self, input_ids, input_mask, segment_ids, label_ids):
        self.input_ids = input_ids
        self.input_mask = input_mask
        self.segment_ids = segment_ids
        self.label_ids = label_ids


def convert_examples_to_features(examples, label_list, max_seq_length, tokenizer, gpt2=False):
    """Loads a data file into a list of `InputBatch`s."""

    label_map = {label: i for i, label in enumerate(label_list)}
    features = []
    multi_label = True
    if all([len(label) == 1 for label in [x.labels for x in examples]]):
        multi_label = False

    for (ex_index, example) in enumerate(examples):
        tokens_a = tokenizer.tokenize(example.text_a)

        tokens_b = None
        if example.text_b:
            tokens_b = tokenizer.tokenize(example.text_b)
            # Modifies `tokens_a` and `tokens_b` in place so that the total
            # length is less than the specified length.
            # Account for [CLS], [SEP], [SEP] with "- 3"
            _truncate_seq_pair(tokens_a, tokens_b, max_seq_length - 3)
        else:
            # Account for [CLS] and [SEP] with "- 2"
            if gpt2:
                if len(tokens_a) > max_seq_length - 1:
                    tokens_a = tokens_a[:(max_seq_length - 1)]
            else:
                if len(tokens_a) > max_seq_length - 2:
                    tokens_a = tokens_a[:(max_seq_length - 2)]

        # The convention in BERT is:
        # (a) For sequence pairs:
        #  tokens:   [CLS] is this jack ##son ##ville ? [SEP] no it is not . [SEP]
        #  type_ids: 0   0  0    0    0     0       0 0    1  1  1  1   1 1
        # (b) For single sequences:
        #  tokens:   [CLS] the dog is hairy . [SEP]
        #  type_ids: 0   0   0   0  0     0 0
        #
        # Where "type_ids" are used to indicate whether this is the first
        # sequence or the second sequence. The embedding vectors for `type=0` and
        # `type=1` were learned during pre-training and are added to the wordpiece
        # embedding vector (and position vector). This is not *strictly* necessary
        # since the [SEP] token unambigiously separates the sequences, but it makes
        # it easier for the model to learn the concept of sequences.
        #
        # For classification tasks, the first vector (corresponding to [CLS]) is
        # used as as the "sentence vector". Note that this only makes sense because
        # the entire model is fine-tuned.
        if gpt2:
            tokens = tokens_a + ["[CLS]"]
        else:
            tokens = ["[CLS]"] + tokens_a + ["[SEP]"]
        segment_ids = [0] * len(tokens)

        if tokens_b:
            tokens += tokens_b + ["[SEP]"]
            segment_ids += [1] * (len(tokens_b) + 1)

        input_ids = tokenizer.convert_tokens_to_ids(tokens)

        # The mask has 1 for real tokens and 0 for padding tokens. Only real
        # tokens are attended to.
        input_mask = [1] * len(input_ids)

        # Zero-pad up to the sequence length.
        padding = [0] * (max_seq_length - len(input_ids))
        input_ids += padding
        input_mask += padding
        segment_ids += padding

        assert len(input_ids) == max_seq_length
        assert len(input_mask) == max_seq_length
        assert len(segment_ids) == max_seq_length

        if not multi_label:
            label_ids = label_map[example.labels[0]]
        else:
            label_ids = [0] * len(label_list)
            for label in example.labels:
                if label != '':
                    label_id = label_map[label]
                    label_ids[label_id] = 1
        if ex_index < 5:
            logger.info("*** Example ***")
            logger.info("guid: %s" % (example.guid))
            logger.info("tokens: %s" % " ".join(
                [str(x) for x in tokens]))
            logger.info("input_ids: %s" % " ".join([str(x) for x in input_ids]))
            logger.info("input_mask: %s" % " ".join([str(x) for x in input_mask]))
            logger.info(
                "segment_ids: %s" % " ".join([str(x) for x in segment_ids]))
            logger.info("labels: %s" % " ".join([str(x) for x in example.labels]))
            if multi_label:
                logger.info("label_ids: %s" % " ".join([str(x) for x in label_ids]))
            else:
                logger.info("label_ids: %s" % str(label_ids))

        features.append(
            InputFeatures(input_ids=input_ids,
                          input_mask=input_mask,
                          segment_ids=segment_ids,
                          label_ids=label_ids))
    return features


def _truncate_seq_pair(tokens_a, tokens_b, max_length):
    """Truncates a sequence pair in place to the maximum length."""

    # This is a simple heuristic which will always truncate the longer sequence
    # one token at a time. This makes more sense than truncating an equal percent
    # of tokens from each, since if one sequence is very short then each token
    # that's truncated likely contains more information than a longer sequence.
    while True:
        total_length = len(tokens_a) + len(tokens_b)
        if total_length <= max_length:
            break
        if len(tokens_a) > len(tokens_b):
            tokens_a.pop()
        else:
            tokens_b.pop()


class DataProcessor():
    """Processor for the Frames data set (Wiki_70k version)."""

    def get_train_examples(self, data_path):
        """See base class."""
        logger.info("LOOKING AT {}".format(data_path))
        return self._create_examples(
            self._read_tsv(data_path), "train")

    def get_dev_examples(self, data_path):
        """See base class."""
        return self._create_examples(
            self._read_tsv(data_path), "dev")

    def get_labels(self, train_path, dev_path):
        """See base class."""
        train_examples = self.get_train_examples(train_path)
        dev_examples = self.get_dev_examples(dev_path)

        labels_2d = [i.labels for i in train_examples] + [i.labels for i in dev_examples]
        labels_2d = [i for i in labels_2d if i != [""]]
        return sorted(list(set([j for sub in labels_2d for j in sub])))

    def _create_examples(self, df, set_type):
        """Creates examples for the training and dev sets."""
        examples = []
        lines = df.to_dict(orient='records')
        for (i, line) in enumerate(lines):
            if i == 0:
                continue
            guid = "%s-%s" % (set_type, i)
            sentence = line["data"]
            labels = line["labels"]
            if str(labels) == "nan":
                labels = ""
            examples.append(
                InputExample(guid=guid, text_a=sentence, labels=str(labels).split(',')))
        return examples

    @classmethod
    def _read_tsv(cls, input_file, quotechar=None):
        """Reads a tab separated value file."""
        return pd.read_csv(input_file, delimiter='\t')


def main():
    parser = argparse.ArgumentParser()

    ## Required parameters
    parser.add_argument("--train_file",
                        default=None,
                        type=str,
                        required=True,
                        help="The train_path.tsv file with headers.")
    parser.add_argument("--eval_file",
                        default=None,
                        type=str,
                        required=True,
                        help="The eval_path.tsv file with headers.")

    parser.add_argument("--model", default=None, type=str, required=True,
                        help="Pre-trained model selected in the list: bert, xlnet, gpt2")

    parser.add_argument("--bert_model", default="bert-base-uncased", type=str, required=False,
                        help="Bert pre-trained model selected in the list: bert-base-uncased, "
                             "bert-large-uncased, bert-base-cased, bert-large-cased, bert-base-multilingual-uncased, "
                             "bert-base-multilingual-cased, bert-base-chinese.")

    parser.add_argument("--xlnet_model", default="xlnet-base-cased", type=str, required=False,
                        help="XLNet pre-trained model selected in the list: xlnet-base-cased, base-base-cased")

    parser.add_argument("--gpt2_model", default="gpt2", type=str, required=False,
                        help="GPT-2 pre-trained model selected in the list: gpt2, gpt2-medium, gpt2-large, gpt2-xl")

    parser.add_argument("--gpt2_classification_type", default="mean", type=str, required=False,
                        help="GPT-2 classification type selected in the list: mean, sum, concat, last, first")

    # parser.add_argument("--output_dir",
    #                     default=None,
    #                     type=str,
    #                     required=True,
    #                     help="The output directory where the model predictions and checkpoints will be written.")
    # parser.add_argument("--init_checkpoint",
    #                     default=None,
    #                     type=str,
    #                     required=True,
    #                     help="The checkpoint file from pretraining")

    ## Other parameters
    parser.add_argument("--train_batch_size",
                        default=32,
                        type=int,
                        help="Total batch size for training.")
    parser.add_argument("--gpu",
                        default=0,
                        type=int,
                        help="GPU to be used.")
    parser.add_argument("--eval_batch_size",
                        default=32,
                        type=int,
                        help="Total batch size for eval.")
    parser.add_argument("--learning_rate",
                        default=2e-5,
                        type=float,
                        help="The initial learning rate for Adam.")
    parser.add_argument("--num_train_epochs",
                        default=4.0,
                        type=float,
                        help="Total number of training epochs to perform.")
    parser.add_argument("--prob_threshold",
                        default=0.5,
                        type=float,
                        help="Probabilty threshold for multiabel classification.")
    parser.add_argument("--max_seq_length",
                        default=128,
                        type=int,
                        help="The maximum total input sequence length after WordPiece tokenization. \n"
                             "Sequences longer than this will be truncated, and sequences shorter \n"
                             "than this will be padded.")
    # parser.add_argument("--do_lower_case",
    #                     action='store_true',
    #                     help="Set this flag if you are using an uncased model.")
    #
    # parser.add_argument('--vocab_file',
    #                     type=str, default=None, required=True,
    #                     help="Vocabulary mapping/file BERT was pretrainined on")
    # parser.add_argument("--config_file",
    #                     default=None,
    #                     type=str,
    #                     required=True,
    #                     help="The BERT model config")

    args = parser.parse_args()
    gpu = args.gpu
    if gpu == -1:
        device = torch.device('cpu')
    else:
        device = torch.device('cuda:'+str(gpu))

    n_gpu = torch.cuda.device_count()
    torch.cuda.set_device(0)
    dp = DataProcessor()

    train_examples = dp.get_train_examples(args.train_file)
    eval_examples = dp.get_dev_examples(args.eval_file)
    labels = dp.get_labels(args.train_file, args.eval_file)

    tokenizers = {
        "bert": BertTokenizer.from_pretrained(args.bert_model, do_lower_case=True),
        "xlnet": XLNetTokenizer.from_pretrained(args.xlnet_model, do_lower_case=True),
        "gpt2": GPT2Tokenizer.from_pretrained(args.gpt2_model)
    }
    tokenizer = tokenizers[args.model]
    if args.model == "gpt2":
        tokenizer.add_special_tokens({'cls_token': '[CLS]'})
    train_features = convert_examples_to_features(
        train_examples, labels, args.max_seq_length, tokenizer, gpt2=args.model=="gpt2")

    all_input_ids = torch.tensor([f.input_ids for f in train_features], dtype=torch.long)
    all_input_mask = torch.tensor([f.input_mask for f in train_features], dtype=torch.long)
    all_segment_ids = torch.tensor([f.segment_ids for f in train_features], dtype=torch.long)
    all_label_ids = torch.tensor([f.label_ids for f in train_features], dtype=torch.long)
    all_labels = [i.labels for i in train_examples]+[i.labels for i in eval_examples]

    multi_label = False

    if all([len(label) == 1 for label in all_labels]):
        models = {
            "bert": BertForSequenceClassification.from_pretrained(args.bert_model, num_labels=len(labels)),
            "xlnet": XLNetForSequenceClassification.from_pretrained(args.xlnet_model, num_labels=len(labels)),
            "gpt2": GPT2ForSequenceClassification.from_pretrained(args.gpt2_model, num_labels=len(labels))
        }
    else:
        models = {
            "bert": BertForMultiLabelSequenceClassification.from_pretrained(args.bert_model, num_labels=len(labels)),
            "xlnet": XLNetForMultiLabelSequenceClassification.from_pretrained(args.xlnet_model, num_labels=len(labels)),
            "gpt2": GPT2ForMultiLabelSequenceClassification.from_pretrained(args.gpt2_model, num_labels=len(labels))
        }
        multi_label = True
    logger.info("device: {} n_gpu: {}".format(
        device, n_gpu))
    model = models[args.model]
    if args.model == "gpt2":
        model.gpt2.resize_token_embeddings(len(tokenizer))
        model.set_type(args.gpt2_classification_type)
    model.to(device)
    train_data = TensorDataset(all_input_ids, all_input_mask, all_segment_ids, all_label_ids)
    train_sampler = RandomSampler(train_data)
    train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=args.train_batch_size)
    global_step = 0
    nb_tr_steps = 0
    tr_loss = 0
    model.train()
    T = args.prob_threshold
    param_optimizer = list(model.named_parameters())
    no_decay = ['bias', 'gamma', 'beta']
    optimizer_grouped_parameters = [
        {'params': [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)],
        'weight_decay_rate': 0.01},
        {'params': [p for n, p in param_optimizer if any(nd in n for nd in no_decay)],
        'weight_decay_rate': 0.0}
    ]

    # This variable contains all of the hyperparemeter information that the training loop needs
    optimizer = AdamW(optimizer_grouped_parameters,
                        lr=args.learning_rate)
    for _ in trange(int(args.num_train_epochs), desc="Epoch"):
        tr_loss = 0
        nb_tr_examples, nb_tr_steps = 0, 0
        for step, batch in enumerate(tqdm(train_dataloader, desc="Iteration")):
            batch = tuple(t.to(device) for t in batch)
            input_ids, input_mask, segment_ids, label_ids = batch
            outputs = model(input_ids = input_ids, token_type_ids = segment_ids, attention_mask = input_mask, labels = label_ids)
            loss = outputs[0]
            loss.backward()

            tr_loss += loss.item()
            nb_tr_examples += input_ids.size(0)
            nb_tr_steps += 1
            global_step += 1
            optimizer.step()
            optimizer.zero_grad()

    eval_features = convert_examples_to_features(
        eval_examples, labels, args.max_seq_length, tokenizer)
    logger.info("***** Running evaluation *****")
    logger.info("  Num examples = %d", len(eval_examples))
    logger.info("  Batch size = %d", args.eval_batch_size)
    all_input_ids = torch.tensor([f.input_ids for f in eval_features], dtype=torch.long)
    all_input_mask = torch.tensor([f.input_mask for f in eval_features], dtype=torch.long)
    all_segment_ids = torch.tensor([f.segment_ids for f in eval_features], dtype=torch.long)
    all_label_ids = torch.tensor([f.label_ids for f in eval_features], dtype=torch.long)
    eval_data = TensorDataset(all_input_ids, all_input_mask, all_segment_ids, all_label_ids)
    # Run prediction for full data
    eval_sampler = SequentialSampler(eval_data)
    eval_dataloader = DataLoader(eval_data, sampler=eval_sampler, batch_size=args.eval_batch_size)

    model.eval()
    eval_loss, eval_accuracy = 0, 0
    nb_eval_steps, nb_eval_examples = 0, 0
    preds = None
    out_label_ids = None
    for input_ids, input_mask, segment_ids, label_ids in tqdm(eval_dataloader, desc="Evaluating"):
        input_ids = input_ids.to(device)
        input_mask = input_mask.to(device)
        segment_ids = segment_ids.to(device)
        label_ids = label_ids.to(device)

        with torch.no_grad():
            outputs = model(input_ids = input_ids, token_type_ids = segment_ids, attention_mask = input_mask, labels = label_ids)[:2]
            #logits = model(input_ids = input_ids, token_type_ids = segment_ids, attention_mask = input_mask)
            tmp_eval_loss = outputs[0]
            logits = outputs[1]
            eval_loss += tmp_eval_loss.mean().item()
        nb_eval_steps += 1
        if preds is None:
            if gpu == -1:
                preds = logits.numpy()
                out_label_ids = label_ids.numpy()
            else:
                preds = logits.detach().cpu().numpy()
                out_label_ids = label_ids.detach().cpu().numpy()
        else:
            if gpu == -1:
                preds = np.append(preds, logits.numpy(), axis=0)
                out_label_ids = np.append(out_label_ids, label_ids.numpy(), axis=0)
            else:
                preds = np.append(preds, logits.detach().cpu().numpy(), axis=0)
                out_label_ids = np.append(out_label_ids, label_ids.detach().cpu().numpy(), axis=0)

    eval_loss = eval_loss / nb_eval_steps

    if multi_label:
        probs = torch.sigmoid(torch.from_numpy(preds))
        # If probability greater than or equal to threshold T the tweet contains that emotion
        preds = (probs >= T).type(torch.FloatTensor)
        if gpu == -1:
            preds = preds.numpy()
        else:
            preds = preds.detach().cpu().numpy()
    else:
        preds = np.argmax(preds, axis=1)
    loss = tr_loss / nb_tr_steps

    results = {'eval_loss': eval_loss,
               'global_step': global_step,
               'loss': loss}

    result = metrics_frame(preds, out_label_ids, labels)
    results.update(result)
    print(results)
    model_name = args.model
    if model_name == "bert":
        model_name = args.bert_model
    elif model_name == "xlnet":
        model_name = args.xlnet_model
    elif model_name == "gpt2":
        model_name = args.gpt2_model
    output_eval_file = "eval_results_" + model_name + "_" + args.train_file.split("/")[-1].split(".")[0] + ".txt"

    with open(output_eval_file, "w") as writer:
        logger.info("***** Eval results *****")
        for key in sorted(results.keys()):
            logger.info("  %s = %s", key, str(results[key]))
            writer.write("%s = %s\n" % (key, str(results[key])))

if __name__ == "__main__":
    main()