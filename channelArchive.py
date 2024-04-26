#!/usr/bin/python3
import os
import fnmatch
from subprocess import call, check_output
import json
import time
import sys
import datetime
from enum import Enum

webServer = None
socketIO = None

channels = []
base_dir = ""
install_dir = ""
youtube_dl_location = "/usr/bin/yt-dlp"
dry_run = False
webui_mode = False
download_in_progress = False
logging_options = []
session_history = []

# Constants
START_MESSAGE = "channelArchive.py - A youtube channel downloader"
SITE_YOUTUBE = "youtube"
SITE_RUMBLE = "rumble"
LOGGING_VERBOSE = "verbose"
LOGGING_DELETED = "deleted"


def main():
    timeStart = time.time()
    loadCommandLineArgs(sys.argv)

    startMessage = "\n" + str(datetime.datetime.now()) + "\n"
    startMessage += START_MESSAGE
    log(startMessage, "high")

    loadConfiguration()

    if webui_mode:
        startWebServer()
    else:
        startDownload()

    timeElapsed = round(time.time() - timeStart, 2)
    log("Finished in " + str(timeElapsed) + " seconds.", "high")


def startDownload():
    global download_in_progress
    global session_history
    download_in_progress = True
    session_history = []
    for channel in channels:
        fetchVideoMetadata(channel)
        downloadVideos(channel)
    download_in_progress = False


def loadConfiguration():
    ###Loads the configuration and channel options from the 'channelArchive.config' file.
    global base_dir
    global install_dir
    install_dir = os.getcwd() + "/"
    config_path = install_dir + "channelArchive.config"
    if not os.path.isfile(config_path):
        config_path = install_dir + "channelArchive.config.example"
        if not os.path.isfile(config_path):
            log("FAILURE - CONFIG FILE NOT FOUND", "high")
            log("Add file channelArchive.config in directory " + install_dir)
            sys.exit(1)
    log("Configuration file found at " + config_path)
    with open(config_path, encoding="utf-8") as file:
        for line in file:
            line = stripWhitespace(line)
            if len(line) == 0:
                continue
            if line[0] == "#":
                continue
            if "base_dir" in line:
                base_dir = line.split("=")[-1]
                base_dir = stripWhitespace(base_dir)
                if base_dir[-1] != "/":
                    base_dir += "/"
                log("Setting base directory to " + base_dir)
            args = ""
            if line[0] == "[":
                channelName = line.split("[")[1].split("]")[0]
                channelID = line.split("[")[2].split("]")[0]
                channelDir = line.split("[")[3].split("]")[0]
                if len(line.split("[")) >= 5:
                    args = line.split("[")[4].split("]")[0]

                if channelDir[-1] != "/":
                    channelDir += "/"
                channel = Channel(channelName, channelID, channelDir, args)
                channels.append(channel)
                # Create Dir if it doesn't exist
                dirToCheck = base_dir + channelDir
                if not os.path.exists(dirToCheck):
                    os.makedirs(dirToCheck)


# reloads the configuration file. used by the web UI
def reloadConfiguration():
    global channels
    channels = []
    log("Reloading configuration file", priority="web")
    loadConfiguration()
    log("Reload successful. found " + str(len(channels)) + " channels.", "web")
    for channel in channels:
        log(str(channel), "web")


def fetchVideoMetadata(channel):
    # Gets all the Video IDs from a channel
    if len(channel.channelURL) <= 0:
        return False
    log("\n" + str(channel), "high")
    videoList = []
    videosFound = 0
    videosToDownload = 0
    videosDeleted = 0
    folder = base_dir + channel.channelDir
    command = [youtube_dl_location, "--flat-playlist", "-j", channel.channelURL]
    try:
        # Parse the JSON output to get list of video IDs from channel
        channelRaw = check_output(command).decode("utf-8").splitlines()
        for line in channelRaw:
            line = json.loads(line)
            if "id" in line:
                video = Video(line["id"], line["title"], channel)
                videoList.append(video)
                videosFound += 1
                videosToDownload += 1

        # Check currently downloaded videos and remove them from the list
        for file in os.listdir(folder):
            fileMatched = (
                False  # Check if downloaded file was matched to a video in the list
            )
            for video in videoList:
                vidString = "*" + video.videoID + "*"
                if fnmatch.fnmatch(file, vidString):
                    fileMatched = True
                    videoList.remove(video)
                    videosToDownload -= 1
            if not fileMatched:
                videosDeleted += 1
                log("Video deleted from channel : " + file, LOGGING_DELETED)
        channel.videos = videoList.copy()
        log("Found " + str(videosDeleted) + " deleted videos.", LOGGING_DELETED)
        log_text = (
            "Downloading "
            + str(videosToDownload)
            + " videos, out of "
            + str(videosFound)
            + " found"
        )
        log(log_text, "high")
    except:
        log("Error downloading videos by " + str(channel))


def downloadVideos(channel):
    # Downloads all the videos from a channel using youtube-dl
    # Relys on channel.videos being set, from the fetchVideoMetadata function
    if len(channel.videos) <= 0:
        log("\nNo videos found for " + str(channel))
        return

    ytdl_log = open(install_dir + "ytdl.log", "a+", encoding="utf-8")
    for i, video in enumerate(channel.videos, start=1):
        log(
            "Downloading video ("
            + str(i)
            + " / "
            + str(len(channel.videos))
            + "): "
            + str(video),
            "high",
        )
        if not dry_run:
            url = "https://www.youtube.com/watch?v=" + video.videoID
            outputFile = (
                base_dir
                + channel.channelDir
                + "%(upload_date)s - %(title)s - %(id)s.%(ext)s"
            )
            ytdl_log = open(install_dir + "ytdl.log", "a+", encoding="utf-8")
            myCall = [
                youtube_dl_location,
                "-o",
                outputFile,
                "--write-thumbnail",
                "-f",
                "best",
                "--cookies",
                install_dir + "cookies.txt",
                "--",
                url,
            ]
            if "--best" in channel.args:
                myCall = [
                    youtube_dl_location,
                    "-o",
                    outputFile,
                    "-f",
                    "((571/272/402/337/315/313/401/336/308/400/271/335/303/299/399/137/248/334/302/298/398/247/136/333/244/135/397/332/243/134/396/331/242/133/395/330/160/394/278)[protocol!=http_dash_segments])+(bestaudio[acodec=opus]/bestaudio[protocol!=http_dash_segments])/best",
                    "--",
                    url,
                ]
            call(myCall, stdout=ytdl_log, stderr=ytdl_log)
            ytdl_log.close()


def loadCommandLineArgs(args):
    global webui_mode
    global dry_run

    for arg in args:
        if arg == "--verbose" or arg == "-v":
            logging_options.append(LOGGING_VERBOSE)
        if arg == "--deleted" or arg == "-d":
            logging_options.append(LOGGING_DELETED)
        if arg == "--web" or arg == "-w":
            webui_mode = True
        if arg == "--dry-run":
            dry_run = True


def startWebServer():
    global webServer
    global socketIO
    try:
        from flask import Flask, send_from_directory
        from flask_socketio import SocketIO

        webServer = Flask(__name__)
        socketIO = SocketIO(webServer)

        @webServer.route("/")
        def main_route():
            return send_from_directory(".", path="index.html")

        @socketIO.on("connect")
        def handle_connect():
            print("Client connected")

        @socketIO.on("startDownload")
        def handle_startDownload():
            if download_in_progress:
                socketIO.emit("response", "ERR400")
            else:
                socketIO.emit("response", START_MESSAGE)
                startDownload()
                session_history.append(str(START_MESSAGE))
                socketIO.emit("response", "Download process finished")
                session_history.append("Download process finished")

        @socketIO.on("reloadConfiguration")
        def handle_reloadConfiguration():
            reloadConfiguration()

        @socketIO.on("fetchSessionHistory")
        def handle_fetchSessionHistory():
            for message in session_history:
                socketIO.emit("response", message)

        socketIO.run(webServer, port=8179, host="0.0.0.0")
    except ImportError:
        log("Failed to load required dependancy: Flask or flask_socketio", "high")


def log(message, priority="low"):
    global webui_mode
    logFile = install_dir + "log"
    with open(logFile, "a+", encoding="utf-8") as file:
        file.write(message + "\n")
    if LOGGING_VERBOSE in logging_options or priority == "high":
        print(message)
        if webui_mode and socketIO != None:
            socketIO.emit("response", message)
            session_history.append(message)
    elif priority == LOGGING_DELETED and LOGGING_DELETED in logging_options:
        print(message)
        if webui_mode and socketIO != None:
            socketIO.emit("response", message)
            session_history.append(message)
    elif webui_mode and socketIO != None and priority == "web":
        socketIO.emit("response", message)
        session_history.append(message)


def stripWhitespace(string):
    return string.strip()


class Sites(Enum):
    YOUTUBE = 1
    RUMBLE = 2


class Channel:
    def __init__(self, channelName, channelID, channelDir, args):
        self.channelName = channelName
        self.channelID = channelID
        self.channelDir = channelDir
        if (
            channelID.startswith("http")
            or channelID.startswith("www")
            or channelID.startswith("youtube.com")
        ):
            self.channelURL = channelID + "/videos"
        else:
            self.channelURL = "https://www.youtube.com/channel/" + channelID + "/videos"
        self.channelURL += "/videos"
        self.playlistURL = ""
        self.videos = []
        self.args = args

    def __str__(self):
        return "[Channel: " + self.channelName + " | ID: " + self.channelID + "]"

    def __repr__(self):
        return "[Channel: " + self.channelName + " | ID: " + self.channelID + "]"


class Video:
    def __init__(self, videoID, title, channel):
        self.videoID = videoID
        self.title = title
        self.channel = channel

    def __str__(self):
        return (
            "Video ID: "
            + self.videoID
            + " | Channel: "
            + self.channel.channelName
            + " | Title: "
            + self.title
        )

    def __repr__(self):
        return (
            "Video ID: "
            + self.videoID
            + " | Channel: "
            + self.channel.channelName
            + " | Title: "
            + self.title
        )


if __name__ == "__main__":
    main()
