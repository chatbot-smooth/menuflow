from __future__ import annotations

from abc import abstractmethod
from enum import Enum
from json import JSONDecodeError, dumps, loads
from typing import Any, Dict, List

from attr import dataclass, ib
from mautrix.types import SerializableAttrs

from ..config import Config
from ..jinja.jinja_template import jinja_env
from ..matrix import MatrixClient
from ..utils.base_logger import BaseLogger


class NodeType(Enum):
    MESSAGE = "message"
    SWITCH = "switch"
    INPUT = "input"
    HTTPREQUEST = "http_request"
    CHECKTIME = "check_time"


@dataclass
class FlowObject(SerializableAttrs, BaseLogger):

    id: str = ib()
    type: NodeType = ib()

    config: Config = None
    client: MatrixClient = None
    flow_variables: Dict[str, Any] = {}

    @classmethod
    def init_cls(cls, config: Config):
        cls.config = config

    @abstractmethod
    async def run(self):
        pass

    def build_node(self):
        return self.deserialize(self.__dict__)

    def render_data(self, data: Dict | List | str, variables: Dict) -> Dict | List | str:
        if self.flow_variables:
            variables.update(self.flow_variables.__dict__)

        if isinstance(data, str):
            data_template = jinja_env.from_string(data)
        else:
            try:
                data_template = jinja_env.from_string(dumps(data))
            except Exception as e:
                self.log.exception(e)
                return

        def convert_to_bool(item):
            if isinstance(item, dict):
                for k, v in item.items():
                    item[k] = convert_to_bool(v)
                return item
            elif isinstance(item, list):
                return [convert_to_bool(i) for i in item]
            elif isinstance(item, str):
                if item in ["True", "true"]:
                    return True
                elif item in ["False", "false"]:
                    return False
                else:
                    return item
            else:
                return item

        try:
            data = loads(data_template.render(**variables))
            data = convert_to_bool(data)
            return data
        except JSONDecodeError:
            data = data_template.render(**variables)
            return convert_to_bool(data)
        except KeyError:
            data = loads(data_template.render())
            data = convert_to_bool(data)
            return data
