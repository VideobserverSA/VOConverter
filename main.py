__author__ = 'Rui'

from tkinter import *
from tkinter import filedialog
import xml.etree.ElementTree as xmlParser
from subprocess import *
import os

ffmpeg_path = "ffmpeg.exe"

root = Tk()

class FileChooser(object):

    def __init__(self):
        btn = Button(text="Open File", command=self.open_dialog)
        btn.pack()

        another = Button(text="Quit", command=self.quit_app)
        another.pack()

    def open_dialog(self):
        fn = filedialog.askopenfilename(filetypes=(("VO Playlist", "*.vopl"),
                                                   ("All Files", "*.*")),
                                        initialdir="C://Users//Rui//Documents//VideoObserver//Playlist"
                                        )
        self.parse_playlist(filename=fn)

    def quit_app(self):
        exit()

    def parse_playlist(self, filename):
        print("INfile>> ", filename)
        tree = xmlParser.parse(filename)
        base = tree.getroot()
        video_path = base.get("video_path")
        video_path = video_path[8:]
        print("VPath>> ", video_path)

        print("")

        cut_number = 0
        # start parsing each item
        for child in base.findall('.items/item'):
            item_type = child.find("type").text
            print("ItemType>> ", item_type)

            time_start = ""
            time_end = ""
            comments = ""

            if item_type == "ga":
                time_start = int(child.find("game_action").find("video_time_start").text)
                time_end = int(child.find("game_action").find("video_time_end").text)
                comments = child.find("game_action").find("comments").text

            print("TimeStart>> ", time_start)
            print("TimeEnd>> ", time_end)
            print("Comments>> ", comments)

            print("")

            duration = time_end - time_start
            tmp_out = os.path.dirname(os.path.realpath(__file__)) + "\\" + str(cut_number) + ".mp4"
            cut_number += 1

            codec = "-c copy -bsf:v h264_mp4toannexb -f mpegts"

            try:
                # out = check_output([ffmpeg_path, args], shell=False)
                out = check_output([
                    # path to ffmpeg
                    ffmpeg_path,
                    # overwrite
                    "-y",
                    # start time
                    "-ss",
                    str(time_start),
                    # input file
                    "-i",
                    video_path,
                    # duration
                    "-t",
                    str(duration),
                    # codec
                    "-c",
                    "copy",
                    "-bsf:v",
                    "h264_mp4toannexb",
                    "-f",
                    "mpegts",
                    # output file
                    tmp_out
                ], shell=False)

            except CalledProcessError as cpe:
                print("ERROR>> ", cpe.output)

        # JOIN THE THINGS
        join_args = []
        # path to ffmpeg
        join_args.append(ffmpeg_path)
        # overwrite
        join_args.append("-y")
        # input
        join_args.append("-i")
        # the concat files
        concat = "concat:"
        for x in range(0, cut_number):
            concat += os.path.dirname(os.path.realpath(__file__)) + "\\" + str(x) + ".mp4" + "|"
        concat = concat[:-1]
        join_args.append(concat)
        # outfile
        join_args.append(os.path.dirname(os.path.realpath(__file__)) + "\\" + "final" + ".mp4")

        try:
            out = check_output(join_args, shell=False)
        except CalledProcessError as cpe:
            print("ERROR>>", cpe.output)

        # DEBUG
        exit()

if __name__ == '__main__':
    fc = FileChooser()
    mainloop()
