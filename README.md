# BureauDesRip

DVDs used to be the shit but now I don't even have a way to play them on my TV
(well I do but I need to find the cables and so on and I'm really lazy to do
so). Instead I've created a folder on my NAS where I can copy my DVD collection
and then watch my favorite series that are not on Netflix through this channel
instead (without having to hear the brrrr and the tchktchktchk from the DVD
player under the TV).

The choice of MKV for this project is quite simple: it can keep the chapters,
supports the bitmap subtitles and overall supports all the things that we like
from DVDs (aka NOT the menu and NOT the 3 minutes copyright disclaimer and
certainly NOT the ads for fuck sake I paid for these things).

Okay so how do you use it?

Once the project is installed in your Python environment, you can simply do
something like:

```
python -m bureaudesrip -o '/media/NAS/My Series Name/' -n 'My Series Name' -t 2=S03E07 3=S03E08
```

This will transcode titles 2 and 3 into `My Series Name — DVDRip — S03E07.mkv`
and `My Series Name — DVDRip — S03E08.mkv` in the `/media/NAS/My Series Name/`
folder and that's about it.

For more information you can either read the `-h` menu (there are more options)
or read the source code. I'm not going to write more about it because I just
write this for myself and I'm using GitHub to back it up.

> _Note_ &mdash; You need for this to work to have HandBrakeCLI installed
> (from the `handbrake-cli` Debian package) and probably the `libdvdcss` lib
> but I'll let you interpret your local law to know if it's legal or not
