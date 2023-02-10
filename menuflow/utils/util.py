from asyncio import Task, all_tasks
from logging import getLogger
from re import match

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from ..config import Config


class Util:
    config: Config
    log: TraceLogger = getLogger("menuflow.util")
    _main_matrix_regex = "[\\w-]+:[\\w.-]"

    def __init__(self, config: Config):
        self.config = config

    @classmethod
    def is_user_id(cls, user_id: UserID) -> bool:
        """It checks if the user_id is valid matrix user_id

        Parameters
        ----------
        user_id : str
            The user ID to check.

        Returns
        -------
            A boolean value.

        """
        return False if not user_id else bool(match(f"^@{cls._main_matrix_regex}+$", user_id))

    @classmethod
    def is_room_id(cls, room_id: RoomID) -> bool:
        """It checks if the room_id is valid matrix room_id

        Parameters
        ----------
        room_id : str
            The room ID to check.

        Returns
        -------
            A boolean value.

        """
        return False if not room_id else bool(match(f"^!{cls._main_matrix_regex}+$", room_id))

    @classmethod
    async def get_tasks_by_name(self, task_name: str) -> Task:
        """It returns a task object from the current event loop, given the task's name
        Parameters
        ----------
        task_name
            The name of the task to find.
        Returns
        -------
            An specific task.
        """

        tasks = all_tasks()
        for task in tasks:
            if task.get_name() == task_name:
                return task

    @classmethod
    async def cancel_inactivity_task(self, room_id: RoomID):
        """It cancels the inactivity task that is running in the background"""

        task = await self.get_tasks_by_name(room_id)
        if task:
            task.cancel()
            self.log.debug(f"TASK CANCEL -> {room_id}")

    def ignore_user(self, mxid: UserID, origin: str) -> bool:
        """It checks if the user ID matches any of the regex patterns in the config file

        Parameters
        ----------
        mxid : UserID
            The user ID of the user who sent the message.
        origin : str
            This is the type of event that triggered the function. It can be one of the following:
            - message
            - invite

        Returns
        -------
            A boolean value.

        """

        user_regex = (
            "menuflow.ignore.messages_from"
            if origin == "message"
            else "menuflow.ignore.invitations_from"
        )

        if self.is_user_id(mxid):
            for pattern in self.config[user_regex]:
                if match(pattern, mxid):
                    return True

        return False
