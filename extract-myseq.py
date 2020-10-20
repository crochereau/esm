#!/usr/bin/env python3 -u
# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import glob
import numpy as np
import os
import pathlib
import torch

from esm import Alphabet, FastaBatchedDataset, ProteinBertModel, pretrained

BASE_PATH = '/Users/charlotterochereau/Documents/Alquraishi/scop175id40_3/'

def create_parser():
    parser = argparse.ArgumentParser(
        description="Extract per-token representations and model outputs for sequences in a FASTA file"  # noqa
    )

    parser.add_argument(
        "model_location",
        type=str,
        help="PyTorch model file OR name of pretrained model to download (see README for models)",
    )
    parser.add_argument(
        "fasta_folder",
        type = str,
        #type=pathlib.Path,
        help="FASTA folder containing files on which to extract representations",
    )
    parser.add_argument(
        "output_dir",
        type=pathlib.Path,
        help="output directory for extracted representations",
    )

    parser.add_argument(
        "--toks_per_batch", type=int, default=4096, help="maximum batch size"
    )
    parser.add_argument(
        "--repr_layers",
        type=int,
        default=[-1],
        nargs="+",
        help="layers indices from which to extract representations (0 to num_layers, inclusive)",
    )
    parser.add_argument(
        "--include",
        type=str,
        nargs="+",
        choices=["mean", "per_tok", "bos"],
        help="specify which representations to return",
        required=True
    )

    parser.add_argument("--nogpu", action="store_true", help="Do not use GPU even if available")
    return parser


def main(args):
    model, alphabet = pretrained.load_model_and_alphabet(args.model_location)
    model.eval()
    if torch.cuda.is_available() and not args.nogpu:
        model = model.cuda()
        print("Transferred model to GPU")
    
    path = BASE_PATH + args.fasta_folder 
    for filename in glob.glob(os.path.join(path, '*.fa')):
        with open(os.path.join(os.getcwd(), filename), 'r') as f:      
            dataset = FastaBatchedDataset.from_file(filename)
            batches = dataset.get_batch_indices(args.toks_per_batch, extra_toks_per_seq=1)
            data_loader = torch.utils.data.DataLoader(
                dataset, collate_fn=alphabet.get_batch_converter(), batch_sampler=batches
            )
            print(f"Read {filename} with {len(dataset)} sequences")

            args.output_dir.mkdir(parents=True, exist_ok=True)

            assert all(
                -(model.num_layers + 1) <= i <= model.num_layers for i in args.repr_layers
            )
            repr_layers = [
                (i + model.num_layers + 1) % (model.num_layers + 1) for i in args.repr_layers
            ]

            with torch.no_grad():
                for batch_idx, (labels, strs, toks) in enumerate(data_loader):
                    print(
                        f"Processing {batch_idx + 1} of {len(batches)} batches ({toks.size(0)} sequences)"
                    )
                    if torch.cuda.is_available() and not args.nogpu:
                        toks = toks.to(device="cuda", non_blocking=True)

                    out = model(toks, repr_layers=repr_layers)
                    logits = out["logits"].to(device="cpu")
                    representations = {
                        layer: t.to(device="cpu") for layer, t in out["representations"].items()
                    }

                    for i, label in enumerate(labels):
                        args.output_file = (
                            args.output_dir / f"{label}"
                        )
                        args.output_file.parent.mkdir(parents=True, exist_ok=True)
                        #result = {"label": label}

                        if "per_tok" in args.include:
                            result["representations"] = {
                                layer: t[i, 1 : len(strs[i]) + 1]
                                for layer, t in representations.items()
                            }

                        if "mean" in args.include:
                            result["mean_representations"] = {
                                layer: t[i, 1 : len(strs[i]) + 1].mean(0)
                                for layer, t in representations.items()
                            }

                        for layer, t in representations.items():
                            res = t[i, 1: len(strs[i]) + 1].mean(0)
                        res.detach().numpy()

                        if "bos" in args.include:
                            result["bos_representations"] = {
                                layer: t[i, 0] for layer, t in representations.items()
                            }

                        np.save(
                            args.output_file,
                            res
                        )

                        torch.save(
                            result,
                            args.output_file,
                        )


if __name__ == "__main__":
    parser = create_parser()
    args = parser.parse_args()
    main(args)