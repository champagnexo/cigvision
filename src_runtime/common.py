# -*- coding: utf-8 -*-
"""Shared logger. Creates the Debug folder if it is missing."""
import logging
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_DIR = os.path.join(BASE_DIR, "..", "Debug")


def SetupLogger(fn, outtoconsole=False):
    os.makedirs(os.path.dirname(os.path.abspath(fn)), exist_ok=True)

    Logger = logging.getLogger("mylogger")
    Logger.handlers.clear()
    Logger.setLevel(logging.DEBUG)
    Logger.propagate = False

    formatter = logging.Formatter("{asctime} - {levelname} - {message}",
                                  style="{", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(fn, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    Logger.addHandler(file_handler)

    if outtoconsole:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        Logger.addHandler(console)

    return Logger


mylogger = SetupLogger(os.path.join(DEBUG_DIR, "mylogger.txt"), outtoconsole=True)
