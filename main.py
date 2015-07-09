__author__ = 'Rui'

from tkinter import *
from tkinter import filedialog
import xml.etree.ElementTree as xmlParser
from subprocess import *
import os
import tempfile
import sys
import urllib.parse
import threading
import time

ffmpeg_path = "ffmpeg.exe"

root = Tk()

class EncodeSubtitles(threading.Thread):

    def __init__(self, temp_dir, cut_number, video_path, time_start, duration, comments, tmp_out):

        super().__init__()

        self.cut_number = cut_number
        self.video_path = video_path
        self.time_start = time_start
        self.duration = duration
        self.comments = comments
        self.tmp_out = tmp_out
        self.temp_dir = temp_dir

    def run(self):
        print("IN THREAD!!!!!!!!!")

        # write srt file
        srt_path = self.temp_dir.name + "\\" + str(self.cut_number) + ".srt"
        srt_file = open(srt_path, "wb")

        srt_log_path = self.temp_dir.name + "\\" + str(self.cut_number) + ".srt.log"
        srt_log_file = open(srt_log_path, "wb")

        log_path = self.temp_dir.name + "\\" + str(self.cut_number) + ".log"
        log_file = open(log_path, "wb")

        srt_contents = "1\n"
        srt_contents += "00:00:00,000" + " --> " + "05:00:00,000" +  "1\n"
        srt_contents += self.comments + "\n"

        srt_file.write(srt_contents.encode("utf8"))
        srt_file.close()

        escaped_srt_path = srt_path.replace("\\", "\\\\").replace(":", "\:").replace(" ", "\ ")

        proc = check_call([
            ffmpeg_path,
            # overwrite
            "-y",
            # input file
            "-i",
            self.video_path,
            # duration
            "-t",
            str(self.duration),
            # codec
            "-codec:v",
            "libx264",
            "-crf",
            "23",
            "-codec:a",
            "copy",
            "-vf",
            "subtitles=" + "'" + escaped_srt_path + "'",
            # start time
            "-ss",
            str(self.time_start),
            self.temp_dir.name + "\\" + str(self.cut_number) + "_srt.mp4"
        ],
            shell=False,
            universal_newlines=True,
            stderr=STDOUT,
            stdout=srt_log_file
        )

        out = check_call([
            # path to ffmpeg
            ffmpeg_path,
            # overwrite
            "-y",
            # start time, since this clip is already we want to use it all
            "-ss",
            "0",
            # input file
            "-i",
            self.temp_dir.name + "\\" + str(self.cut_number) + "_srt.mp4",
            # duration
            "-t",
            str(self.duration),
            # codec
            "-c",
            "copy",
            "-bsf:v",
            "h264_mp4toannexb",
            "-f",
            "mpegts",
            # output file
            self.tmp_out
        ],  stderr=STDOUT,
            stdout=log_file,
            shell=False)

        print("END END TH")

class FileChooser(object):

    def __init__(self):
        btn = Button(text="Open File", command=self.open_dialog)
        btn.pack()

        self.meter = Meter(root, bg="white", fillcolor="light blue")
        self.meter.pack()

        another = Button(text="Quit", command=self.quit_app)
        another.pack()

        self.temp_dir = tempfile.TemporaryDirectory()
        self.num_items = 0

        self.base_name = ""

    def open_dialog(self):

        initial_dir = os.path.expanduser("~/Documents/VideoObserver/Playlist")

        fn = filedialog.askopenfilename(filetypes=(("VO Playlist", "*.vopl"),
                                                   ("All Files", "*.*")),
                                        initialdir=initial_dir
                                        )
        self.parse_playlist(filename=fn)

    def quit_app(self):

        # Cleanup
        self.temp_dir.cleanup()

        sys.exit(0)

    def parse_playlist(self, filename):

        # to keep the cut files

        # we have a name so make sure we create the dir
        if not os.path.exists(self.temp_dir.name):
            os.makedirs(self.temp_dir.name)

        print("INfile>> ", filename)
        tree = xmlParser.parse(filename)
        base = tree.getroot()
        # if the file name has spaces we end up with %20 in the url
        video_path = urllib.parse.unquote(base.get("video_path"))

        self.base_name = base.get("name")
        if self.base_name is None:
            self.base_name = os.path.basename(filename)

        # get playlist length
        play_len = len(base.findall('.items/item'))
        print("NItems>> ", play_len)
        # we say that the join is the last step
        play_len += 1
        self.num_items = play_len
        self.meter.set(0.0, "Converting: " + self.base_name + " " + "0%")

        # now if we have the file:/// present we remove it
        video_path = video_path.replace("file:///", "")

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
            enable_comments = True

            if item_type == "ga":
                time_start = int(float(child.find("game_action").find("video_time_start").text))
                time_end = int(float(child.find("game_action").find("video_time_end").text))
                comments = child.find("game_action").find("comments").text
                ec = child.find("game_action").find("comments_enabled")
                if ec is not None:
                    enable_comments = ec.text

            if item_type == "cue":
                time_start = int(float(child.find("action_cue").find("starting_time").text))
                time_end = int(float(child.find("action_cue").find("ending_time").text))
                comments = child.find("action_cue").find("comments").text
                ec = child.find("action_cue").find("comments_enabled")
                if ec is not None:
                    enable_comments = ec.text

            # add some padding
            # time_start += 2
            # time_end += 2

            print("TimeStart>> ", time_start)
            print("TimeEnd>> ", time_end)
            print("Comments>> ", comments)
            print("Enable Comments>> ", enable_comments)

            print("")

            duration = time_end - time_start
            tmp_out = self.temp_dir.name + "\\" + str(cut_number) + ".mp4"

            try:

                if comments is None or enable_comments == "false":

                    log_path = self.temp_dir.name + "\\" + str(cut_number) + ".log"
                    log_file = open(log_path, "wb")

                    out = check_call([
                        # path to ffmpeg
                        ffmpeg_path,
                        # overwrite
                        "-y",
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
                         # start time
                        "-ss",
                        str(time_start),
                        # output file
                        tmp_out
                        ],
                        stderr=STDOUT,
                        stdout=log_file,
                        shell=False)
                    # calc progress
                    progress = (cut_number / self.num_items)
                    self.meter.set(progress, "Converting: " + self.base_name + " " + str((progress * 100)) + "%")
                else:
                    print("BEFORE TH")

                    sub_thr = EncodeSubtitles(temp_dir=self.temp_dir, cut_number=cut_number, video_path=video_path,
                                              time_start=time_start, duration=duration, comments=comments,
                                              tmp_out=tmp_out)

                    sub_thr.start()

                    # sub_thr = threading.Thread(target=self.encode_with_subtitles, args=[
                    #     cut_number,
                    #     video_path,
                    #     time_start,
                    #     duration,
                    #     comments,
                    #     tmp_out
                    # ])
                    #sub_thr.start()
                    #sub_thr.join()
                    #sub_thr.run()

                    while sub_thr.is_alive():
                        time.sleep(1)
                        print("sleeping...")

                    progress = (cut_number / self.num_items)
                    self.meter.set(progress, "Converting: " + self.base_name + " " + str((progress * 100)) + "%")

                    #sub_thr.join()
                    print("AFTER TH")

            except CalledProcessError as cpe:
                print("ERROR>> ", cpe.output)

            cut_number += 1

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
            concat += self.temp_dir.name + "\\" + str(x) + ".mp4" + "|"
        concat = concat[:-1]
        join_args.append(concat)

        # fast copy concatneation
        join_args.append("-c")
        join_args.append("copy")
        join_args.append("-bsf:a")
        join_args.append("aac_adtstoasc")
        join_args.append("-movflags")
        join_args.append("faststart")

        # outfile
        out_filename = self.base_name.replace(".vopl", "")
        # put it on desktop for now
        desktop_dir = os.path.expanduser("~/Desktop/")
        join_args.append(desktop_dir + "\\" + out_filename + ".mp4")

        print("JOINARGS>>", ' '.join(join_args))

        join_log_path = self.temp_dir.name + "\\" + "join.log"
        join_log_file = open(join_log_path, "wb")

        try:
            out = check_call(join_args, stderr=STDOUT, stdout=join_log_file, shell=False)
        except CalledProcessError as cpe:
            print("ERROR>>", cpe.output)

        self.meter.set(1, "Done: " + self.base_name + " " + "100" + "%")

        # DEBUG
        # sys.exit(0)

# CODE FOR PROGRESS BAR
class Meter(Frame):
    def __init__(self, master, width=300, height=20, bg='white', fillcolor='orchid1',
                 value=0.0, text=None, font=None, textcolor='black', *args, **kw):
        Frame.__init__(self, master, bg=bg, width=width, height=height, *args, **kw)
        self._value = value

        self._canv = Canvas(self, bg=self['bg'], width=self['width'], height=self['height'],
                            highlightthickness=0, relief='flat', bd=0)
        self._canv.pack(fill='both', expand=1)
        self._rect = self._canv.create_rectangle(0, 0, 0, self._canv.winfo_reqheight(), fill=fillcolor,
                                                 width=0)
        self._text = self._canv.create_text(self._canv.winfo_reqwidth()/2, self._canv.winfo_reqheight()/2,
                                            text='', fill=textcolor)
        if font:
            self._canv.itemconfigure(self._text, font=font)

        self.set(value, text)
        self.bind('<Configure>', self._update_coords)

    def _update_coords(self, event):
        # Updates the position of the text and rectangle inside the canvas when the size of
        # the widget gets changed.
        # looks like we have to call update_idletasks() twice to make sure
        # to get the results we expect
        self._canv.update_idletasks()
        self._canv.coords(self._text, self._canv.winfo_width()/2, self._canv.winfo_height()/2)
        self._canv.coords(self._rect, 0, 0, self._canv.winfo_width()*self._value, self._canv.winfo_height())
        self._canv.update_idletasks()

    def get(self):
        return self._value, self._canv.itemcget(self._text, 'text')

    def set(self, value=0.0, text=None):
        # make the value failsafe:
        if value < 0.0:
            value = 0.0
        elif value > 1.0:
            value = 1.0
        self._value = value
        if text == None:
            # if no text is specified use the default percentage string:
            text = str(int(round(100 * value))) + ' %'
        self._canv.coords(self._rect, 0, 0, self._canv.winfo_width()*value, self._canv.winfo_height())
        self._canv.itemconfigure(self._text, text=text)
        self._canv.update_idletasks()

if __name__ == '__main__':
    fc = FileChooser()
    mainloop()
