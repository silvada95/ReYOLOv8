# Ultralytics YOLO 🚀, GPL-3.0 license
import contextlib
import re
import shutil
import sys
from difflib import get_close_matches
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Union

from ultralytics.yolo.utils import (DEFAULT_CFG, DEFAULT_CFG_DICT, DEFAULT_CFG_PATH, LOGGER, ROOT, USER_CONFIG_DIR,
                                    IterableSimpleNamespace, __version__, checks, colorstr, yaml_load, yaml_print)

CLI_HELP_MSG = \
    f"""
    ReYOLOv8 - a modified Ultralytics YOLOv8 detector for Event-Based Object Detection
    
  
    To refer to the original YOLOv8:
    
    Docs: https://docs.ultralytics.com/cli
    Community: https://community.ultralytics.com
    GitHub: https://github.com/ultralytics/ultralytics
    """
CFG_FLOAT_KEYS = {'warmup_epochs', 'box', 'cls', 'dfl', 'max_zoom_out_factor', 'min_zoom_out_factor'}
CFG_FRACTION_KEYS = {'iou', 'lr0', 'lrf', 'momentum', 'weight_decay', 'warmup_momentum', 'warmup_bias_lr', 'fl_gamma', 'conf', 'iou', 'zoom_out', 'invert',
'positive', 'suppress', 'flip', 'invert' }
CFG_INT_KEYS = {'batchs_init', 'val_epoch', 'channels', 'clip_length', 'clip_stride',
    'epochs', 'patience', 'batch', 'workers', 'seed','max_det',
    'line_thickness', 'workspace', 'nbs', 'save_period', 'val_epoch', 'channels'}
CFG_BOOL_KEYS = {
    'save', 'exist_ok', 'pretrained', 'verbose', 'deterministic','val', 'half', 'dnn', 'plots', 'show', 'save_txt', 'save_conf',
    'save_crop', 'hide_labels', 'hide_conf', 'visualize', 'augment', 'boxes', 
    'optimize', 'dynamic', 'rect', 'speed', 'zero_hidden'}


def cfg2dict(cfg):
    """
    Convert a configuration object to a dictionary, whether it is a file path, a string, or a SimpleNamespace object.

    Inputs:
        cfg (str) or (Path) or (SimpleNamespace): Configuration object to be converted to a dictionary.

    Returns:
        cfg (dict): Configuration object in dictionary format.
    """
    if isinstance(cfg, (str, Path)):
        cfg = yaml_load(cfg)  # load dict
        print(cfg)
    elif isinstance(cfg, SimpleNamespace):
        cfg = vars(cfg)  # convert to dict
    return cfg


def get_cfg(cfg: Union[str, Path, Dict, SimpleNamespace] = DEFAULT_CFG_DICT, overrides: Dict = None):
    """
    Load and merge configuration data from a file or dictionary.

    Args:
        cfg (str) or (Path) or (Dict) or (SimpleNamespace): Configuration data.
        overrides (str) or (Dict), optional: Overrides in the form of a file name or a dictionary. Default is None.

    Returns:
        (SimpleNamespace): Training arguments namespace.
    """
    cfg = cfg2dict(cfg)

    # Merge overrides
    if overrides:
        overrides = cfg2dict(overrides)
        check_cfg_mismatch(cfg, overrides)
        cfg = {**cfg, **overrides}  # merge cfg and overrides dicts (prefer overrides)

    # Special handling for numeric project/names
    for k in 'project', 'name':
        if k in cfg and isinstance(cfg[k], (int, float)):
            cfg[k] = str(cfg[k])

    # Type and Value checks
    for k, v in cfg.items():
        if v is not None:  # None values may be from optional args
            if k in CFG_FLOAT_KEYS and not isinstance(v, (int, float)):
                raise TypeError(f"'{k}={v}' is of invalid type {type(v).__name__}. "
                                f"Valid '{k}' types are int (i.e. '{k}=0') or float (i.e. '{k}=0.5')")
            elif k in CFG_FRACTION_KEYS:
                if not isinstance(v, (int, float)):
                    raise TypeError(f"'{k}={v}' is of invalid type {type(v).__name__}. "
                                    f"Valid '{k}' types are int (i.e. '{k}=0') or float (i.e. '{k}=0.5')")
                if not (0.0 <= v <= 1.0):
                    raise ValueError(f"'{k}={v}' is an invalid value. "
                                     f"Valid '{k}' values are between 0.0 and 1.0.")
            elif k in CFG_INT_KEYS and not isinstance(v, int):
                raise TypeError(f"'{k}={v}' is of invalid type {type(v).__name__}. "
                                f"'{k}' must be an int (i.e. '{k}=8')")
            elif k in CFG_BOOL_KEYS and not isinstance(v, bool):
                raise TypeError(f"'{k}={v}' is of invalid type {type(v).__name__}. "
                                f"'{k}' must be a bool (i.e. '{k}=True' or '{k}=False')")

    # Return instance
    return IterableSimpleNamespace(**cfg)


def check_cfg_mismatch(base: Dict, custom: Dict, e=None):
    """
    This function checks for any mismatched keys between a custom configuration list and a base configuration list.
    If any mismatched keys are found, the function prints out similar keys from the base list and exits the program.

    Inputs:
        - custom (Dict): a dictionary of custom configuration options
        - base (Dict): a dictionary of base configuration options
    """
    base, custom = (set(x.keys()) for x in (base, custom))
    mismatched = [x for x in custom if x not in base]
    if mismatched:
        string = ''
        for x in mismatched:
            matches = get_close_matches(x, base)  # key list
            matches = [f'{k}={DEFAULT_CFG_DICT[k]}' if DEFAULT_CFG_DICT.get(k) is not None else k for k in matches]
            match_str = f'Similar arguments are i.e. {matches}.' if matches else ''
            string += f"'{colorstr('red', 'bold', x)}' is not a valid YOLO argument. {match_str}\n"
        raise SyntaxError(string + CLI_HELP_MSG) from e


def merge_equals_args(args: List[str]) -> List[str]:
    """
    Merges arguments around isolated '=' args in a list of strings.
    The function considers cases where the first argument ends with '=' or the second starts with '=',
    as well as when the middle one is an equals sign.

    Args:
        args (List[str]): A list of strings where each element is an argument.

    Returns:
        List[str]: A list of strings where the arguments around isolated '=' are merged.
    """
    new_args = []
    for i, arg in enumerate(args):
        if arg == '=' and 0 < i < len(args) - 1:  # merge ['arg', '=', 'val']
            new_args[-1] += f'={args[i + 1]}'
            del args[i + 1]
        elif arg.endswith('=') and i < len(args) - 1 and '=' not in args[i + 1]:  # merge ['arg=', 'val']
            new_args.append(f'{arg}{args[i + 1]}')
            del args[i + 1]
        elif arg.startswith('=') and i > 0:  # merge ['arg', '=val']
            new_args[-1] += arg
        else:
            new_args.append(arg)
    return new_args


def entrypoint(debug=''):
    """
    This function is the ultralytics package entrypoint, it's responsible for parsing the command line arguments passed
    to the package.

    This function allows for:
    - passing mandatory YOLO args as a list of strings
    - specifying the task to be performed, either 'detect', 'segment' or 'classify'
    - specifying the mode, either 'train', 'val', 'test', or 'predict'
    - running special modes like 'checks'
    - passing overrides to the package's configuration

    It uses the package's default cfg and initializes it using the passed overrides.
    Then it calls the CLI function with the composed cfg
    """
    args = (debug.split(' ') if debug else sys.argv)[1:]
    if not args:  # no arguments passed
        LOGGER.info(CLI_HELP_MSG)
        return

    # Define tasks and modes
    tasks = 'detect', 'segment', 'classify'
    modes = 'train', 'val', 'predict', 'export', 'track'
    special = {
        'help': lambda: LOGGER.info(CLI_HELP_MSG),
        'checks': checks.check_yolo,
        'version': lambda: LOGGER.info(__version__),
        'settings': lambda: yaml_print(USER_CONFIG_DIR / 'settings.yaml'),
        'cfg': lambda: yaml_print(DEFAULT_CFG_PATH),
        'copy-cfg': copy_default_cfg}
    full_args_dict = {**DEFAULT_CFG_DICT, **{k: None for k in tasks}, **{k: None for k in modes}, **special}

    # Define common mis-uses of special commands, i.e. -h, -help, --help
    special.update({k[0]: v for k, v in special.items()})  # singular
    special.update({k[:-1]: v for k, v in special.items() if len(k) > 1 and k.endswith('s')})  # singular
    special = {**special, **{f'-{k}': v for k, v in special.items()}, **{f'--{k}': v for k, v in special.items()}}

    overrides = {}  # basic overrides, i.e. imgsz=320
    for a in merge_equals_args(args):  # merge spaces around '=' sign
        if a.startswith('--'):
            LOGGER.warning(f"WARNING ⚠️ '{a}' does not require leading dashes '--', updating to '{a[2:]}'.")
            a = a[2:]
        if '=' in a:
            try:
                re.sub(r' *= *', '=', a)  # remove spaces around equals sign
                k, v = a.split('=', 1)  # split on first '=' sign
                assert v, f"missing '{k}' value"
                if k == 'cfg':  # custom.yaml passed
                    LOGGER.info(f'Overriding {DEFAULT_CFG_PATH} with {v}')
                    overrides = {k: val for k, val in yaml_load(v).items() if k != 'cfg'}
                else:
                    if v.lower() == 'none':
                        v = None
                    elif v.lower() == 'true':
                        v = True
                    elif v.lower() == 'false':
                        v = False
                    else:
                        with contextlib.suppress(Exception):
                            v = eval(v)
                    overrides[k] = v
            except (NameError, SyntaxError, ValueError, AssertionError) as e:
                check_cfg_mismatch(full_args_dict, {a: ''}, e)

        elif a in tasks:
            overrides['task'] = a
        elif a in modes:
            overrides['mode'] = a
        elif a in special:
            special[a]()
            return
        elif a in DEFAULT_CFG_DICT and isinstance(DEFAULT_CFG_DICT[a], bool):
            overrides[a] = True  # auto-True for default bool args, i.e. 'yolo show' sets show=True
        elif a in DEFAULT_CFG_DICT:
            raise SyntaxError(f"'{colorstr('red', 'bold', a)}' is a valid YOLO argument but is missing an '=' sign "
                              f"to set its value, i.e. try '{a}={DEFAULT_CFG_DICT[a]}'\n{CLI_HELP_MSG}")
        else:
            check_cfg_mismatch(full_args_dict, {a: ''})

    # Defaults
    task2model = dict(detect='yolov8n.pt', segment='yolov8n-seg.pt', classify='yolov8n-cls.pt')
    task2data = dict(detect='coco128.yaml', segment='coco128-seg.yaml', classify='imagenet100')

    # Mode
    mode = overrides.get('mode', None)
    if mode is None:
        mode = DEFAULT_CFG.mode or 'predict'
        LOGGER.warning(f"WARNING ⚠️ 'mode' is missing. Valid modes are {modes}. Using default 'mode={mode}'.")
    elif mode not in modes:
        if mode not in ('checks', checks):
            raise ValueError(f"Invalid 'mode={mode}'. Valid modes are {modes}.\n{CLI_HELP_MSG}")
        LOGGER.warning("WARNING ⚠️ 'yolo mode=checks' is deprecated. Use 'yolo checks' instead.")
        checks.check_yolo()
        return

    # Model
    model = overrides.pop('model', DEFAULT_CFG.model)
    task = overrides.pop('task', None)
    if model is None:
        model = task2model.get(task, 'yolov8n.pt')
        LOGGER.warning(f"WARNING ⚠️ 'model' is missing. Using default 'model={model}'.")
    from ultralytics.yolo.engine.model import YOLO
    overrides['model'] = model
    model = YOLO(model)

    # Task
    if task and task != model.task:
        LOGGER.warning(f"WARNING ⚠️ 'task={task}' conflicts with {model.task} model {overrides['model']}. "
                       f"Inheriting 'task={model.task}' from {overrides['model']} and ignoring 'task={task}'.")
    task = model.task
    overrides['task'] = task
    if mode in {'predict', 'track'} and 'source' not in overrides:
        overrides['source'] = DEFAULT_CFG.source or ROOT / 'assets' if (ROOT / 'assets').exists() \
            else 'https://ultralytics.com/images/bus.jpg'
        LOGGER.warning(f"WARNING ⚠️ 'source' is missing. Using default 'source={overrides['source']}'.")
    elif mode in ('train', 'val'):
        if 'data' not in overrides:
            overrides['data'] = task2data.get(task, DEFAULT_CFG.data)
            LOGGER.warning(f"WARNING ⚠️ 'data' is missing. Using {model.task} default 'data={overrides['data']}'.")
    elif mode == 'export':
        if 'format' not in overrides:
            overrides['format'] = DEFAULT_CFG.format or 'torchscript'
            LOGGER.warning(f"WARNING ⚠️ 'format' is missing. Using default 'format={overrides['format']}'.")

    # Run command in python
    # getattr(model, mode)(**vars(get_cfg(overrides=overrides)))  # default args using default.yaml
    getattr(model, mode)(**overrides)  # default args from model


# Special modes --------------------------------------------------------------------------------------------------------
def copy_default_cfg():
    new_file = Path.cwd() / DEFAULT_CFG_PATH.name.replace('.yaml', '_copy.yaml')
    shutil.copy2(DEFAULT_CFG_PATH, new_file)
    LOGGER.info(f'{DEFAULT_CFG_PATH} copied to {new_file}\n'
                f"Example YOLO command with this new custom cfg:\n    yolo cfg='{new_file}' imgsz=320 batch=8")


if __name__ == '__main__':
    # entrypoint(debug='yolo predict model=yolov8n.pt')
    entrypoint(debug='')
