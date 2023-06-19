from typing import Dict, Optional, Any, List
import json
import enum
import traceback
import base64
import io

import cv2
import gradio as gr
import pydantic
import numpy as np
from PIL import Image

import modules.scripts as scripts
from modules.api.models import (
    StableDiffusionImg2ImgProcessingAPI,
    StableDiffusionTxt2ImgProcessingAPI,
)
from modules.processing import (
    StableDiffusionProcessing,
    StableDiffusionProcessingImg2Img,
)


def img_to_data_url(img: np.ndarray) -> str:
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    iobuf = io.BytesIO()
    pil_img.save(iobuf, format="png")
    binary_img = iobuf.getvalue()

    # Convert raw image to base64
    base64_img = base64.b64encode(binary_img)
    base64_img_str = base64_img.decode("utf-8")

    # Convert base64 to data URL
    return "data:image/png;base64," + base64_img_str


def make_json_compatible(value: Any) -> Any:
    def is_jsonable(x):
        try:
            json.dumps(x, allow_nan=False)
            return True
        except (TypeError, OverflowError, ValueError):
            return False

    if is_jsonable(value):
        return value

    if isinstance(value, dict):
        return {k: make_json_compatible(v) for k, v in value.items()}

    if any(isinstance(value, t) for t in (set, list, tuple)):
        return [make_json_compatible(v) for v in value]

    if isinstance(value, enum.Enum):
        return make_json_compatible(value.value)

    if isinstance(value, np.ndarray):
        return img_to_data_url(value)

    if hasattr(value, "__dict__"):
        return make_json_compatible(vars(value))

    if value in (float("inf"), float("-inf")):
        return None

    print(f"Error: Cannot convert {value} to JSON compatile format.")
    return None


def selectable_script_payload(p: StableDiffusionProcessing) -> Dict:
    """
    Get payload for selectable script based on the provided processing object.

    Args:
        p (StableDiffusionProcessing): Processing object containing script information.

    Returns:
        dict: A dictionary with the name of the selected script and its arguments. If no script is selected,
        the function returns a dictionary with 'None' as the script name and an empty list for script arguments.
    """
    script_runner: scripts.ScriptRunner = p.scripts

    selectable_script_index = p.script_args[0]
    if selectable_script_index == 0:
        return {"script_name": None, "script_args": []}

    selectable_script: scripts.Script = script_runner.selectable_scripts[
        selectable_script_index - 1
    ]
    return {
        "script_name": selectable_script.title().lower(),
        "script_args": p.script_args[
            selectable_script.args_from : selectable_script.args_to
        ],
    }


def alwayson_script_payload(p: StableDiffusionProcessing) -> Dict:
    """
    Get payloads for always-on scripts based on the provided processing object.

    Args:
        p (StableDiffusionProcessing): Processing object containing script information.

    Returns:
        dict: A dictionary with all always-on scripts along with their arguments.
    """
    script_runner: scripts.ScriptRunner = p.scripts

    all_scripts: Dict[str, List] = {}
    for alwayson_script in script_runner.alwayson_scripts:
        all_scripts[alwayson_script.title()] = {
            "args": p.script_args[alwayson_script.args_from : alwayson_script.args_to]
        }
    return {"alwayson_scripts": all_scripts}


def seed_enable_extras_payload(p: StableDiffusionProcessing) -> Dict:
    """
    Determine if seed extras should be enabled based on the provided processing object.

    Args:
        p (StableDiffusionProcessing): Processing object containing seed information.

    Returns:
        dict: A dictionary indicating if seed extras should be enabled.
    """
    return {
        "seed_enable_extras": not (
            p.subseed == -1
            and p.subseed_strength == 0
            and p.seed_resize_from_h == 0
            and p.seed_resize_from_w == 0
        )
    }


def api_payload_dict(
    p: StableDiffusionProcessing, api_request: pydantic.BaseModel
) -> Dict:
    """Get the API payload as a JSON compatible dict.
    Argument:
        api_request(pydantic.BaseModel): The corresponding api request model, either
            - StableDiffusionTxt2ImgProcessingAPI
            - StableDiffusionImg2ImgProcessingAPI
    Returns:
        JSON compatible dict representing the API payload.
    """
    excluded_params = [
        # Following params are optional. The effect can be achieved by passing
        # hr_upscale_to_x/y and with/height.
        "firstphase_width",
        "firstphase_height",
        # Deprecated field.
        "sampler_index",
        # Optional fields.
        "send_images",
        "save_images",
    ]

    result = {}
    # Populate scripts information.
    result.update(selectable_script_payload(p))
    result.update(alwayson_script_payload(p))
    result.update(seed_enable_extras_payload(p))

    for name in api_request.__fields__.keys():
        if name in result or name in excluded_params:
            continue

        if not hasattr(p, name):
            print(f"Warning: field {name} in API payload not found in {p}.")
            continue

        value = getattr(p, name)
        if value is None:
            continue
        result[name] = value

    return make_json_compatible(result)


def format_payload(payload: Optional[Dict]) -> str:
    if payload is None:
        return "No Payload Found"
    return json.dumps(payload, sort_keys=True, allow_nan=False)


class Script(scripts.Script):
    def __init__(self) -> None:
        super().__init__()
        self.json_content: Optional[gr.HTML] = None
        self.api_payload: Optional[Dict] = None

    def title(self) -> str:
        return "API payload"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img: bool) -> List:
        """this function should create gradio UI elements. See https://gradio.app/docs/#components
        The return value should be an array of all components that are used in processing.
        Values of those returned components will be passed to run() and process() functions.
        """
        process_type_prefix = "img2img" if is_img2img else "txt2img"

        with gr.Accordion(
            f"API payload", open=False, elem_classes=["api-payload-display"]
        ):
            # When front-end triggers this click event, data from backend will
            # be pushed to front-end.
            pull_button = gr.Button(
                visible=False,
                elem_classes=["api-payload-pull"],
                elem_id=f"{process_type_prefix}-api-payload-pull",
            )
            gr.HTML(value='<div class="api-payload-json-tree"></div>')
            self.json_content = gr.Textbox(
                elem_classes=["api-payload-content"], visible=False
            )

        pull_button.click(
            lambda: gr.Textbox.update(value=format_payload(self.api_payload)),
            inputs=[],
            outputs=[self.json_content],
        )
        return []

    def process(self, p: StableDiffusionProcessing, *args):
        """
        This function is called before processing begins for AlwaysVisible scripts.
        You can modify the processing object (p) here, inject hooks, etc.
        args contains all values returned by components from ui()
        """
        is_img2img = isinstance(p, StableDiffusionProcessingImg2Img)
        api_request = (
            StableDiffusionImg2ImgProcessingAPI
            if is_img2img
            else StableDiffusionTxt2ImgProcessingAPI
        )
        try:
            self.api_payload = api_payload_dict(p, api_request)
        except Exception as e:
            tb_str = traceback.format_exception(
                etype=type(e), value=e, tb=e.__traceback__
            )
            self.api_payload = {
                "Exception": str(e),
                "Traceback": "".join(tb_str),
            }
