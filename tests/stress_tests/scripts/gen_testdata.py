#!/usr/bin/env python3

# Copyright (C) 2018-2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

""" Script to generate XML config file with the list of IR models
Usage: 
    python gen_testdata.py  --test_conf <name_test_config>.xml  --ir_cache_dir <path_to_ir_cache>
    optional: --framework=[tf|tf2|onnx|pytorch] --precision=[INT8|FP16|FP32] --topology=<model_name_1>,<model_name_2>,... --refs_conf <reference_config>.xml ("references_config.xml" by default) --not_topology=<model_name_1>,<model_name_2>,...
"""
# pylint:disable=line-too-long

import argparse
import json
import logging as log
import os
import shutil
import subprocess
import sys
from shutil import copytree
from inspect import getsourcefile
from pathlib import Path
import defusedxml.ElementTree as ET
import xml.etree.ElementTree as eET
import random

class ListAction(argparse.Action):
  def __init__(self, option_strings, dest, nargs=None, **kwargs):
    if nargs is not None:
      raise ValueError('nargs not allowed')
    super(ListAction, self).__init__(option_strings, dest, **kwargs)

  def __call__(self, parser, namespace, values, option_string=None):
    values = [x.strip() for x in values.split(',')]
    setattr(namespace, self.dest, values)


log.basicConfig(format="{file}: [ %(levelname)s ] %(message)s".format(file=os.path.basename(__file__)),
                level=log.INFO, stream=sys.stdout)


def abs_path(relative_path):
    """Return absolute path given path relative to the current file.
    """
    return os.path.realpath(
        os.path.join(os.path.dirname(getsourcefile(lambda: 0)), relative_path))


def run_in_subprocess(cmd, check_call=True):
    """Runs provided command in attached subprocess."""
    log.info(cmd)
    if check_call:
        subprocess.check_call(cmd, shell=True)
    else:
        subprocess.call(cmd, shell=True)


def get_model_recs(test_conf_root):
    """Parse models from test config.
       Model records in multi-model configs with static test definition are members of "device" sections
    """
    device_recs = test_conf_root.findall("device")
    if device_recs:
        model_recs = []
        for device_rec in device_recs:
            for model_rec in device_rec.findall("model"):
                model_recs.append(model_rec)

        return model_recs

    return test_conf_root.find("models")


def get_ref_recs(ref_conf_root):
    """Parse references from ref config.
    """
    return ref_conf_root.find("models")


def get_args(parser):
    """Parse command line options
    """
    parser.add_argument('--test_conf', required=True, type=Path,
                        help='Path to a test config .xml file to generate IR-models '
                             'list from the directory with IR data cache.')
    parser.add_argument('--refs_conf', required=False, type=Path,
                        help='Path to a reference config .xml file '
                             'list with reference values.')
    parser.add_argument('--ir_cache_dir', type=Path,
                        default=abs_path('../ir_cache'),
                        help='Directory with IR data cache.')
    parser.add_argument('--topology', action=ListAction, default='',
                        help="'List of models topology in IR-cache. Example: --topology=<model_name_1>,<model_name_2>,..."
                        )
    parser.add_argument('--framework', action=ListAction, default='',
                        help="'List of models frameworks in IR-cache. Example: --framework=onnx,tf,pytorch,..."
                        )
    parser.add_argument('--precision', action=ListAction, default='',
                        help="'Precision of models in IR-cache. Example: --precision=INT8,FP16,FP32..."
                        )
    parser.add_argument('--not_topology', action=ListAction, default='',
                        help="'List of models excluded from topology. Example: --not_topology=<model_name_1>,<model_name_2>,..."
                        )
    return parser.parse_args()

def main():
    """Main entry point.
    """
    parser = argparse.ArgumentParser(description='Acquire test data',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    args = get_args(parser)
    test_conf_obj = ET.parse(str(args.test_conf))
    model_recs = get_model_recs(test_conf_obj.getroot()) # <class 'xml.etree.ElementTree.Element'>

    refs_conf_name = "references_config.xml"
    if args.refs_conf:
        refs_conf_name = str(args.refs_conf)
    refs_conf_obj = ET.parse(refs_conf_name)
    ref_recs = get_ref_recs(refs_conf_obj.getroot()) # <class 'xml.etree.ElementTree.Element'>
    
    if not os.path.exists(args.ir_cache_dir):
        raise FileNotFoundError("Directory 'ir_cache_dir' was not found.")
    
    subdirectory = str(args.ir_cache_dir)

    for root, _, files in os.walk(subdirectory):
        for file_name in files:
            full_path = os.path.join(root, file_name)
            path_parts = os.path.normpath(full_path).split(os.path.sep)
            if file_name.endswith(".xml"):
                if args.topology:
                    if file_name.split('.')[0] not in args.topology:
                        continue
                if args.not_topology:
                    if file_name.split('.')[0] in args.not_topology:
                        continue
                if args.framework:
                    _fw = path_parts[-6] if path_parts[-2] != "optimized" else path_parts[-8]
                    if _fw not in args.framework:
                        continue
                if args.precision:
                    _pr = path_parts[-4] if path_parts[-2] != "optimized" else path_parts[-5]
                    if _pr not in args.precision:
                        continue
                
                model_element = eET.Element("model", {
                    "name": file_name,
                    "precision": path_parts[-4] if path_parts[-2] != "optimized" else path_parts[-5],
                    "framework": path_parts[-6] if path_parts[-2] != "optimized" else path_parts[-8],
                    "path": full_path, #subdirectory,
                    "full_path": full_path
                })
                model_element.tail = '\n\t'
                model_recs.append(model_element)
                
                reference_element = eET.Element("model", {
                    "path": full_path, #subdirectory,
                    #"full_path": full_path,
                    "precision": path_parts[-4] if path_parts[-2] != "optimized" else path_parts[-5],
                    "test": "create_exenetwork",
                    "device": "CPU",
                    "vmsize": str(random.randint(1, 1103949)),
                    "vmpeak": str(random.randint(1, 1103949)),
                    "vmrss" : str(random.randint(1, 129329)),
                    "vmhwm" : str(random.randint(1, 129329))
                })
                reference_element.tail = '\n\t'
                ref_recs.append(reference_element)
                
                reference_element = eET.Element("model", {
                    "path": full_path, #subdirectory,
                    #"full_path": full_path,
                    "precision": path_parts[-4] if path_parts[-2] != "optimized" else path_parts[-5],
                    "test": "inference_with_streams",
                    "device": "CPU",
                    "vmsize": str(random.randint(1, 1103949)),
                    "vmpeak": str(random.randint(1, 1103949)),
                    "vmrss" : str(random.randint(1, 129329)),
                    "vmhwm" : str(random.randint(1, 129329))
                })
                reference_element.tail = '\n\t'
                ref_recs.append(reference_element)

                reference_element = eET.Element("model", {
                    "path": full_path, #subdirectory,
                    #"full_path": full_path,
                    "precision": path_parts[-4] if path_parts[-2] != "optimized" else path_parts[-5],
                    "test": "infer_request_inference",
                    "device": "CPU",
                    "vmsize": str(random.randint(1, 1103949)),
                    "vmpeak": str(random.randint(1, 1103949)),
                    "vmrss" : str(random.randint(1, 129329)),
                    "vmhwm" : str(random.randint(1, 129329))
                })
                reference_element.tail = '\n\t'
                ref_recs.append(reference_element)
    
    test_conf_obj.write(args.test_conf, xml_declaration=True)
    refs_conf_obj.write(refs_conf_name, xml_declaration=True)

if __name__ == "__main__":
    main()
