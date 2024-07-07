
This is a fork of the [Rope](https://github.com/Hillobar/Rope/) project (by Hillobar), which focus on implementing features for live swapping using Webcam and for live streaming the swapped videos using virtual camera.

For a full list of features and details, please visit the original project [page](https://github.com/Hillobar/Rope/)

## Additional Features in this Fork: ##

* Includes a lot of awesome mods created Alucard24, Corza, Glat0s and others. You can check out Alucard's fork with those mods [here](https://github.com/Alucard24/Rope/)
* Supports using Live Webcam feed as a video source for swapping
* Supports sending the swapped video as Virtual Camera output (in realtime) which can be used in external applications like Google Meet, Zoom, Twitch etc..
* Integrates Rope with OBS Studio for real-time recording with microphone or computer audio

## Requirements
  * Windows 10 or 11
  * Nvidia GPU with CUDA Support
  * [Git for Windows](https://git-scm.com/download/win)
  * [Miniconda](https://docs.anaconda.com/miniconda/)
  * [OBS Studio](https://obsproject.com/)
  * [FFMPEG](https://www.ffmpeg.org/download.html)

## Screenshots

![](https://i.ibb.co/fCLSjt0/Screenshot-609.png)


## Installation

**Disclaimer**:
This repository is only intended for use on Windows (with Nvidia CUDA).

1. Open a folder in file explorer to install Rope. Once you're in that folder, you can right-click it and select, 'Open in Terminal'

2. Clone the repository to your folder:

```
git clone https://github.com/argenspin/Rope-Live.git
cd Rope-Live
```

3. Create a new conda env and install required libraries

```
# create a conda venv with the correct python version
conda create -n Rope-Live python=3.10.13

# activate the virtual environment
conda activate Rope-Live

# install the dependencies
conda install conda-forge::cuda-runtime=11.8.0 cudnn=8.9.2.26 conda-forge::gputil=1.4.0
python -m pip install -r requirements.txt
```





4. Download the required models
  
   - **To get access to all the features of Rope**, you need to [download the models from here](https://1drv.ms/f/c/f07a89314d38026c/Enes7ZCoMdJEu2XY5ZsDQYwBRgR3J6Cgry3R7LMHm4bz_Q?e=Pbhhzc). You need all of the files.
  
   - Place the downloaded model files in the `Rope-Live/models` folder

5. Set up OBS Virtual Camera
   - Start OBS.
   - Click "Start Virtual Camera" (bottom right), then "Stop Virtual Camera".
   - Close OBS.

7. Start the application by running ***Rope.bat*** file
  





  
