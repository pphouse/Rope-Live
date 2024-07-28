import os
import cv2
import tkinter as tk
from PIL import Image, ImageTk
import threading
import time
import numpy as np
from skimage import transform as trans
import subprocess
from math import floor, ceil
import bisect
import onnxruntime
import torchvision
from torchvision.transforms.functional import normalize #update to v2
import torch
from torchvision import transforms
torchvision.disable_beta_transforms_warning()
from torchvision.transforms import v2
torch.set_grad_enabled(False)
onnxruntime.set_default_logger_severity(4)
import rope.FaceUtil as faceutil

import inspect #print(inspect.currentframe().f_back.f_code.co_name, 'resize_image')
import pyvirtualcam
import platform
device = 'cuda'

# cap = cv2.VideoCapture(0)
# cap_virt = pyvirtualcam.Camera(width=1920, height=1080, fps=1)

lock=threading.Lock()

class VideoManager():  
    def __init__(self, models ):
        self.virtcam = False
        self.models = models
        # Model related
        self.swapper_model = []             # insightface swapper model
        # self.faceapp_model = []             # insight faceapp model
        self.input_names = []               # names of the inswapper.onnx inputs
        self.input_size = []                # size of the inswapper.onnx inputs

        self.output_names = []              # names of the inswapper.onnx outputs    
        self.arcface_dst = np.array( [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)     

        self.video_file = []

        self.FFHQ_kps = np.array([[ 192.98138, 239.94708 ], [ 318.90277, 240.1936 ], [ 256.63416, 314.01935 ], [ 201.26117, 371.41043 ], [ 313.08905, 371.15118 ] ])
        
     
        
        #Video related
        self.capture = []                   # cv2 video
        self.is_video_loaded = False        # flag for video loaded state    
        self.video_frame_total = None       # length of currently loaded video
        self.play = False                   # flag for the play button toggle
        self.current_frame = 0              # the current frame of the video
        self.create_video = False
        self.output_video = []       
        self.file_name = []       

        
        # Play related
        # self.set_read_threads = []          # Name of threaded function
        self.frame_timer = 0.0      # used to set the framerate during playing
        
        # Queues
        self.action_q = []                  # queue for sending to the coordinator
        self.frame_q = []                   # queue for frames that are ready for coordinator

        self.r_frame_q = []                 # queue for frames that are requested by the GUI
        self.read_video_frame_q = []
        
        # swapping related
        # self.source_embedding = []          # array with indexed source embeddings

        self.found_faces = []   # array that maps the found faces to source faces    

        self.parameters = []


        self.target_video = []

        self.fps = 1.0
        self.temp_file = []


        self.clip_session = []

        self.start_time = []
        self.record = False
        self.output = []
        self.image = []

        self.saved_video_path = []
        self.sp = []
        self.timer = []
        self.fps_average = []
        self.total_thread_time = 0.0
        
        self.start_play_time = []
        self.start_play_frame = []
        
        self.rec_thread = []
        self.markers = []
        self.is_image_loaded = False
        self.stop_marker = -1
        self.perf_test = False

        self.control = []

        



        self.process_q =    {
                            "Thread":                   [],
                            "FrameNumber":              [],
                            "ProcessedFrame":           [],
                            "Status":                   'clear',
                            "ThreadTime":               []
                            }   
        self.process_qs = []
        self.rec_q =    {
                            "Thread":                   [],
                            "FrameNumber":              [],
                            "Status":                   'clear'
                            }   
        self.rec_qs = []

        # Face Landmarks
        self.face_landmarks = []
        #
        
    def assign_found_faces(self, found_faces):
        self.found_faces = found_faces

    def enable_virtualcam(self):
        #Check if capture contains any cv2 stream or is it an empty list
        if not isinstance(self.capture, (list)):
            vid_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            vid_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.disable_virtualcam()
            try:
                self.virtcam = pyvirtualcam.Camera(width=vid_width, height=vid_height, fps=self.fps)
            except Exception as e:
                print(e)
    def disable_virtualcam(self):
        if self.virtcam:
            self.virtcam.close()
        self.virtcam = False
        # print("Disable hello")
    def webcam_selected(self, file):
        return ('Webcam' in file) and len(file)==8
    
    def change_webcam_resolution_and_fps(self):
        if self.video_file:
            if self.webcam_selected(self.video_file):
                if self.play:
                    self.play_video('stop')
                    time.sleep(1)
                self.load_target_video(self.video_file)
                self.add_action('clear_faces_stop_swap', None)

    def load_target_video(self, file):
        if self.capture:
            self.capture.release()
        
        if self.control['VirtualCameraSwitch']:
            self.add_action("set_virtual_cam_toggle_disable",None)
            self.disable_virtualcam()

            
        self.video_file = file
        if self.webcam_selected(file):
            webcam_index = int(file[-1])
            if platform.system() == 'Windows':
                try:
                    self.capture = cv2.VideoCapture(webcam_index, cv2.CAP_DSHOW)
                except:
                    self.capture = cv2.VideoCapture(webcam_index)
            else:
                self.capture = cv2.VideoCapture(webcam_index)

            res_width, res_height = self.parameters['WebCamMaxResolSel'].split('x')
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(res_width))
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(res_height))
            self.fps = self.parameters['WebCamMaxFPSSel']
        elif file.lower() == 'obs virtual camera':
            self.capture = cv2.VideoCapture(self.find_obs_virtual_camera())
            self.fps = self.capture.get(cv2.CAP_PROP_FPS)
        else:
            self.capture = cv2.VideoCapture(file)
            self.fps = self.capture.get(cv2.CAP_PROP_FPS)

        if not self.capture.isOpened():
            print("Cannot open file: ", file)
        else:
            self.target_video = file
            self.is_video_loaded = True
            self.is_image_loaded = False
            if not self.webcam_selected(file) and file.lower() != 'obs virtual camera':
                self.video_frame_total = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
            else:
                self.video_frame_total = 99999999
            self.play = False 
            self.current_frame = 0
            self.frame_timer = time.time()
            self.frame_q = []            
            self.r_frame_q = []             
            self.found_faces = []
            self.add_action("set_slider_length",self.video_frame_total-1)

        self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)        
        success, image = self.capture.read() 
        
        if success:
            crop = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # RGB
            temp = [crop, False]
            self.r_frame_q.append(temp)
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)

            if self.face_landmarks:
                self.face_landmarks.remove_all_data()
                self.face_landmarks.apply_landmarks_to_widget_and_parameters(self.current_frame, 1)

    def find_obs_virtual_camera(self):
        for i in range(10):  # 最大10個のカメラをチェック
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    name = cap.getBackendName()
                    if 'OBS Virtual Camera' in name:
                        cap.release()
                        return i
            cap.release()
        return -1  # OBS仮想カメラが見つからない場合

    def load_target_image(self, file):
        if self.capture:
            self.capture.release()
        self.is_video_loaded = False
        self.play = False 
        self.frame_q = []            
        self.r_frame_q = [] 
        self.found_faces = []
        self.image = cv2.imread(file) # BGR
        self.image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB) # RGB
        temp = [self.image, False]
        self.frame_q.append(temp)

        if self.face_landmarks:
            self.face_landmarks.remove_all_data()
            self.face_landmarks.apply_landmarks_to_widget_and_parameters(self.current_frame, 1)

        self.is_image_loaded = True

    
    ## Action queue
    def add_action(self, action, param):
        temp = [action, param]
        self.action_q.append(temp)    
    
    def get_action_length(self):
        return len(self.action_q)

    def get_action(self):
        action = self.action_q[0]
        self.action_q.pop(0)
        return action
     
    ## Queues for the Coordinator
    def get_frame(self):
        frame = self.frame_q[0]
        self.frame_q.pop(0)
        return frame
    
    def get_frame_length(self):
        return len(self.frame_q)  
        
    def get_requested_frame(self):
        frame = self.r_frame_q[0]
        self.r_frame_q.pop(0)
        return frame
    
    def get_requested_frame_length(self):
        return len(self.r_frame_q)          
    

    def get_requested_video_frame(self, frame, marker=True):  
        temp = []
        if self.is_video_loaded:
        
            if self.play == True:            
                self.play_video("stop")
                self.process_qs = []

            apply_landmarks = (self.current_frame != int(frame))
            self.current_frame = int(frame)

            self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            success, target_image = self.capture.read() #BGR

            if success:
                if apply_landmarks and self.face_landmarks:
                    self.face_landmarks.apply_landmarks_to_widget_and_parameters(self.current_frame, 1)
                
                target_image = cv2.cvtColor(target_image, cv2.COLOR_BGR2RGB) #RGB 
                if not self.control['SwapFacesButton']:   
                    temp = [target_image, self.current_frame] #temp = RGB
                else:
                    temp = [self.swap_video(target_image, self.current_frame, marker), self.current_frame] # temp = RGB

                self.r_frame_q.append(temp)
        elif self.is_image_loaded:
            if not self.control['SwapFacesButton']:
                temp = [self.image, self.current_frame] # image = RGB
        
            else:  
                temp = [self.swap_video(self.image, self.current_frame, False), self.current_frame] # image = RGB
            
            self.r_frame_q.append(temp)

    def find_lowest_frame(self, queues):
        min_frame=999999999
        index=-1
        
        for idx, thread in enumerate(queues):
            frame = thread['FrameNumber']
            if frame != []:
                if frame < min_frame:
                    min_frame = frame
                    index=idx
        return index, min_frame


    def play_video(self, command):
        if command == "play":
            self.play = True
            self.fps_average = []            
            self.process_qs = []
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            self.frame_timer = time.time()
            
            for i in range(self.parameters['ThreadsSlider']):
                    new_process_q = self.process_q.copy()
                    self.process_qs.append(new_process_q)
                    
            
            if self.control['AudioButton']:  
                seek_time = (self.current_frame)/self.fps
                args =  ["ffplay", 
                        '-vn', 
                        '-ss', str(seek_time),
                        '-nodisp',
                        '-stats',
                        '-loglevel',  'quiet', 
                        '-sync',  'audio',
                        '-af', f'atempo={self.parameters["AudioSpeedSlider"]}',
                        self.video_file]
 
                self.audio_sp = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                while True:
                    temp = self.audio_sp.stdout.read(69)
                    if temp[:7] != b'    nan':
                        try:
                            sought_time = float(temp[:7].strip()) 
                            self.current_frame = int(self.fps*sought_time)
                            
                            self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
                        except Exception as e:
                            print(e)
                        break

        elif command == "stop":
            self.play = False
            self.add_action("stop_play", True)
            
            index, min_frame = self.find_lowest_frame(self.process_qs)
            
            if index != -1:
                self.current_frame = min_frame-1   
            
            if self.control['AudioButton']: 
                self.add_action('stop_ffplay', None)

            torch.cuda.empty_cache()
                
        elif command=='stop_from_gui':
            self.play = False

            index, min_frame = self.find_lowest_frame(self.process_qs)
            if index != -1:
                self.current_frame = min_frame-1   
            
            if self.control['AudioButton']:    
                self.add_action('stop_ffplay', None)

            torch.cuda.empty_cache()

        elif command == "record":
            self.record = True
            self.play = True
            self.total_thread_time = 0.0
            self.process_qs = []
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            
            for i in range(self.parameters['ThreadsSlider']):
                    new_process_q = self.process_q.copy()
                    self.process_qs.append(new_process_q)

           # Initialize
            self.timer = time.time()
            frame_width = int(self.capture.get(3))
            frame_height = int(self.capture.get(4))

            self.start_time = float(self.capture.get(cv2.CAP_PROP_POS_FRAMES) / float(self.fps))            
            
            self.file_name = os.path.splitext(os.path.basename(self.target_video))
            base_filename =  self.file_name[0]+"_"+str(time.time())[:10]
            self.output = os.path.join(self.saved_video_path, base_filename)
            self.temp_file = self.output+"_temp"+self.file_name[1]  
            
            if self.parameters['RecordTypeTextSel']=='FFMPEG':
                args =  ["ffmpeg", 
                        '-hide_banner',
                        '-loglevel',    'error',
                        "-an",       
                        "-r",           str(self.fps),
                        "-i",           "pipe:",
                        "-vf",          "format=yuvj420p",
                        "-c:v",         "libx264",
                        "-crf",         str(self.parameters['VideoQualSlider']),
                        "-r",           str(self.fps),
                        "-s",           str(frame_width)+"x"+str(frame_height),
                        self.temp_file]  

                self.sp = subprocess.Popen(args, stdin=subprocess.PIPE)
            
            elif self.parameters['RecordTypeTextSel']=='OPENCV':    
                size = (frame_width, frame_height)
                self.sp = cv2.VideoWriter(self.temp_file,  cv2.VideoWriter_fourcc(*'mp4v') , self.fps, size) 
      
    def process(self):
        process_qs_len = range(len(self.process_qs))

        if self.play == True and self.is_video_loaded == True:
            for item in self.process_qs:
                if item['Status'] == 'clear' and self.current_frame < self.video_frame_total:
                    item['Thread'] = threading.Thread(target=self.thread_video_read, args = [self.current_frame]).start()
                    item['FrameNumber'] = self.current_frame
                    item['Status'] = 'started'
                    item['ThreadTime'] = time.time()

                    self.current_frame += 1
                    break
          
        else:
            self.play = False

        time_diff = time.time() - self.frame_timer

        if not self.record and time_diff >= 1.0/float(self.fps) and self.play:

            index, min_frame = self.find_lowest_frame(self.process_qs)

            if index != -1:
                if self.process_qs[index]['Status'] == 'finished':
                    temp = [self.process_qs[index]['ProcessedFrame'], self.process_qs[index]['FrameNumber']]
                    self.frame_q.append(temp)

                    self.fps_average.append(1.0/time_diff)
                    avg_fps = self.fps / self.fps_average[-1] if self.fps_average else 10

                    if self.control['VirtualCameraSwitch'] and self.virtcam:
                        try:
                            self.virtcam.send(temp[0])
                            self.virtcam.sleep_until_next_frame()
                        except Exception as e:
                            print(e)
                    if len(self.fps_average) >= floor(self.fps):
                        fps = round(np.average(self.fps_average), 2)
                        msg = "%s fps, %s process time" % (fps, round(self.process_qs[index]['ThreadTime'], 4))
                        self.fps_average = []

                    if self.process_qs[index]['FrameNumber'] >= self.video_frame_total-1 or self.process_qs[index]['FrameNumber'] == self.stop_marker:
                        self.play_video('stop')
                        
                    self.process_qs[index]['Status'] = 'clear'
                    self.process_qs[index]['Thread'] = []
                    self.process_qs[index]['FrameNumber'] = []
                    self.process_qs[index]['ThreadTime'] = []
                    self.frame_timer += 1.0/self.fps

        if not self.webcam_selected(self.video_file):           
            if self.record:
            
                index, min_frame = self.find_lowest_frame(self.process_qs)           
                
                if index != -1:
                # If the swapper thread has finished generating a frame
                    if self.process_qs[index]['Status'] == 'finished':
                        image = self.process_qs[index]['ProcessedFrame']  
                        
                        if self.parameters['RecordTypeTextSel']=='FFMPEG':

                            pil_image = Image.fromarray(image)
                            pil_image.save(self.sp.stdin, 'BMP')   
                        
                        elif self.parameters['RecordTypeTextSel']=='OPENCV':
                            self.sp.write(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

                        temp = [image, self.process_qs[index]['FrameNumber']]
                        self.frame_q.append(temp)

                        if self.process_qs[index]['FrameNumber'] >= self.video_frame_total-1 or self.process_qs[index]['FrameNumber'] == self.stop_marker or self.play == False:
                            self.play_video("stop")
                            stop_time = float(self.capture.get(cv2.CAP_PROP_POS_FRAMES) / float(self.fps))
                            if stop_time == 0:
                                stop_time = float(self.video_frame_total) / float(self.fps)
                            
                            if self.parameters['RecordTypeTextSel']=='FFMPEG':
                                self.sp.stdin.close()
                                self.sp.wait()
                            elif self.parameters['RecordTypeTextSel']=='OPENCV':    
                                self.sp.release()

                            orig_file = self.target_video
                            final_file = self.output+self.file_name[1]
                            print("adding audio...")    
                            args = ["ffmpeg",
                                    '-hide_banner',
                                    '-loglevel',    'error',
                                    "-i", self.temp_file,
                                    "-ss", str(self.start_time), "-to", str(stop_time), "-i",  orig_file,
                                    "-c",  "copy", # may be c:v
                                    "-map", "0:v:0", "-map", "1:a:0?",
                                    "-shortest",
                                    final_file]
                            
                            four = subprocess.run(args)
                            os.remove(self.temp_file)

                            timef= time.time() - self.timer 
                            self.record = False
                            print('Video saved as:', final_file)
                            msg = "Total time: %s s." % (round(timef,1))
                            print(msg)

                            
                        self.total_thread_time = []
                        self.process_qs[index]['Status'] = 'clear'
                        self.process_qs[index]['FrameNumber'] = []
                        self.process_qs[index]['Thread'] = []
                        self.frame_timer = time.time()
        else:
            self.record=False  
            self.add_action('disable_record_button', False)  
     
    def thread_video_read(self, frame_number):  
        with lock:
            success, target_image = self.capture.read()

        if success:
            target_image = cv2.cvtColor(target_image, cv2.COLOR_BGR2RGB)
            if not self.control['SwapFacesButton']:
                temp = [target_image, frame_number]
            
            else:
                temp = [self.swap_video(target_image, frame_number, True), frame_number]
            
            for item in self.process_qs:
                if item['FrameNumber'] == frame_number:
                    item['ProcessedFrame'] = temp[0]
                    item['Status'] = 'finished'
                    item['ThreadTime'] = time.time() - item['ThreadTime']
                    break


    def swap_video(self, target_image, frame_number, use_markers):
        parameters = self.parameters.copy()
        control = self.control.copy()
        
        if self.markers and use_markers:
            temp=[]
            for i in range(len(self.markers)):
                temp.append(self.markers[i]['frame'])
            idx = bisect.bisect(temp, frame_number)

            if idx > 0:
                parameters = self.markers[idx-1]['parameters'].copy()
        
        img = torch.from_numpy(target_image.astype('uint8')).to('cuda') #HxWxc
        img = img.permute(2,0,1)#cxHxW        
        
        img_x = img.size()[2]
        img_y = img.size()[1]

        det_scale = 1.0
        if img_x<512 and img_y<512:
            if img_x <= img_y:
                new_height = int(512*img_y/img_x)
                tscale = v2.Resize((new_height, 512), antialias=True)
            else:
                new_height = 512
                tscale = v2.Resize((new_height, int(512*img_x/img_y)), antialias=True)

            img = tscale(img)

            det_scale = torch.div(new_height, img_y)
            
        elif img_x<512:
            new_height = int(512*img_y/img_x)
            tscale = v2.Resize((new_height, 512), antialias=True)
            img = tscale(img)

            det_scale = torch.div(new_height, img_y)
        
        elif img_y<512:
            new_height = 512
            tscale = v2.Resize((new_height, int(512*img_x/img_y)), antialias=True)
            img = tscale(img)

            det_scale = torch.div(new_height, img_y)

        if parameters['OrientSwitch']:
            img = v2.functional.rotate(img, angle=parameters['OrientSlider'], interpolation=v2.InterpolationMode.BILINEAR, expand=True)

        if parameters["AutoRotationSwitch"]:
            rotation_angles = [0, 90, 180, 270]
        else:
            rotation_angles = [0]
        bboxes, kpss = self.func_w_test("detect", self.models.run_detect, img, parameters['DetectTypeTextSel'], max_num=20, score=parameters['DetectScoreSlider']/100.0, use_landmark_detection=parameters['LandmarksDetectionAdjSwitch'], landmark_detect_mode=parameters["LandmarksDetectTypeTextSel"], landmark_score=parameters["LandmarksDetectScoreSlider"]/100.0, from_points=parameters["LandmarksAlignModeFromPointsSwitch"], rotation_angles=rotation_angles)

        ret = []
        face_id = 0
        for face_kps in kpss:
            face_id+=1
            if self.face_landmarks and parameters['LandmarksPositionAdjSwitch']:
                landmarks = self.face_landmarks.get_landmarks(frame_number, face_id)
                if landmarks is not None:                    
                    face_kps[0][0] += landmarks[0][0]
                    face_kps[0][1] += landmarks[0][1]
                    face_kps[1][0] += landmarks[1][0]
                    face_kps[1][1] += landmarks[1][1]
                    face_kps[2][0] += landmarks[2][0]
                    face_kps[2][1] += landmarks[2][1]
                    face_kps[3][0] += landmarks[3][0]
                    face_kps[3][1] += landmarks[3][1]
                    face_kps[4][0] += landmarks[4][0]
                    face_kps[4][1] += landmarks[4][1]

            face_emb, _ = self.func_w_test('recognize',  self.models.run_recognize, img, face_kps, self.parameters["SimilarityTypeTextSel"], self.parameters['FaceSwapperModelTextSel'])
            ret.append([face_kps, face_emb])
        
        if ret:
            for fface in ret:
                for found_face in self.found_faces:
                    sim = self.findCosineDistance(fface[1], found_face["Embedding"])
                    if sim>=float(parameters["ThresholdSlider"]) and found_face["SourceFaceAssignments"]:
                        s_e = found_face["AssignedEmbedding"]
                        img_orig = torch.clone(img)
                        img = self.func_w_test("swap_video", self.swap_core, img, fface[0], s_e, fface[1], parameters, control)
                        if parameters['RestoreEyesSwitch']:
                            try:
                                img = self.restore_eyes(img_orig,img,fface[0], parameters['RestoreEyesSlider']/100, parameters['RestoreEyesFeatherSlider'], parameters['RestoreEyesSizeSlider'])
                            except Exception as e:
                                pass
                        if parameters['RestoreMouthSwitch']:
                            try:
                                img = self.restore_mouth(img_orig,img,fface[0], parameters['RestoreMouthSlider']/100, parameters['RestoreMouthFeatherSlider'], parameters['RestoreMouthSizeSlider']/100)
                            except Exception as e:
                                pass
            img = img.permute(1,2,0)
            if not control['MaskViewButton'] and parameters['OrientSwitch']:
                img = img.permute(2,0,1)
                img = transforms.functional.rotate(img, angle=-parameters['OrientSlider'], expand=True)
                img = img.permute(1,2,0)

        else:
            img = img.permute(1,2,0)
            if parameters['OrientSwitch']:
                img = img.permute(2,0,1)
                img = v2.functional.rotate(img, angle=-parameters['OrientSlider'], interpolation=v2.InterpolationMode.BILINEAR, expand=True)
                img = img.permute(1,2,0)
        
        if self.perf_test:
            print('------------------------')  
        
        if img_x <512 or img_y < 512:
            tscale = v2.Resize((img_y, img_x), antialias=True)
            img = img.permute(2,0,1)
            img = tscale(img)
            img = img.permute(1,2,0)
            

        img = img.cpu().numpy()  

        if parameters["ShowLandmarksSwitch"]:
            if ret:
                if img_y <= 720:
                    p = 1
                else:
                    p = 2

                face_id = 0
                for face in ret:
                    face_id += 1
                    if parameters['LandmarksPositionAdjSwitch'] and parameters['FaceIDSlider'] == face_id:
                        kcolor = tuple((255, 0, 0))
                    else:
                        kcolor = tuple((0, 255, 255))
                    for kpoint in face[0]:
                        kpoint = kpoint / det_scale
                        for i in range(-1, p):
                            for j in range(-1, p):
                                try:
                                    img[int(kpoint[1])+i][int(kpoint[0])+j][0] = kcolor[0]
                                    img[int(kpoint[1])+i][int(kpoint[0])+j][1] = kcolor[1]
                                    img[int(kpoint[1])+i][int(kpoint[0])+j][2] = kcolor[2]
                                except:
                                    print("Key-points value {} exceed the image size {}.".format(kpoint, (img_x, img_y)))
                                    continue
        return img.astype(np.uint8)

    def findCosineDistance(self, vector1, vector2):
        vector1 = vector1.ravel()
        vector2 = vector2.ravel()
        cos_dist = 1.0 - np.dot(vector1, vector2)/(np.linalg.norm(vector1)*np.linalg.norm(vector2)) # 2..0

        return 100.0-cos_dist*50.0

    def func_w_test(self, name, func, *args, **argsv):
        timing = time.time()
        result = func(*args, **argsv)
        if self.perf_test:
            print(name, round(time.time()-timing, 5), 's')
        return result

    # @profile    
    def swap_core(self, img, kps, s_e, t_e, parameters, control): # img = RGB
        swapper_model = parameters['FaceSwapperModelTextSel']

        if swapper_model != 'GF1' and swapper_model != 'GF2' and swapper_model != 'GF3':
            # 512 transforms
            dst = self.arcface_dst * 4.0
            dst[:,0] += 32.0
            
            # Change the ref points
            if parameters['FaceAdjSwitch']:
                dst[:,0] += parameters['KPSXSlider']
                dst[:,1] += parameters['KPSYSlider']
                dst[:,0] -= 255
                dst[:,0] *= (1+parameters['KPSScaleSlider']/100)
                dst[:,0] += 255
                dst[:,1] -= 255
                dst[:,1] *= (1+parameters['KPSScaleSlider']/100)
                dst[:,1] += 255

            tform = trans.SimilarityTransform()
            tform.estimate(kps, dst)
        else:
            dst = faceutil.get_arcface_template(image_size=512, mode='arcfacemap')

            # Change the ref points
            if parameters['FaceAdjSwitch']:
                for k in dst:
                    k[:,0] += parameters['KPSXSlider']
                    k[:,1] += parameters['KPSYSlider']
                    k[:,0] -= 255
                    k[:,0] *= (1+parameters['KPSScaleSlider']/100)
                    k[:,0] += 255
                    k[:,1] -= 255
                    k[:,1] *= (1+parameters['KPSScaleSlider']/100)
                    k[:,1] += 255

            M, _ = faceutil.estimate_norm_arcface_template(kps, src=dst)
            tform = trans.SimilarityTransform()
            tform.params[0:2] = M

        # Scaling Transforms
        t512 = v2.Resize((512, 512), interpolation=v2.InterpolationMode.BILINEAR, antialias=False)
        t256 = v2.Resize((256, 256), interpolation=v2.InterpolationMode.BILINEAR, antialias=False)
        t128 = v2.Resize((128, 128), interpolation=v2.InterpolationMode.BILINEAR, antialias=False)

        # Grab 512 face from image and create 256 and 128 copys
        original_face_512 = v2.functional.affine(img, tform.rotation*57.2958, (tform.translation[0], tform.translation[1]) , tform.scale, 0, center = (0,0), interpolation=v2.InterpolationMode.BILINEAR )
        original_face_512 = v2.functional.crop(original_face_512, 0,0, 512, 512)# 3, 512, 512
        original_face_256 = t256(original_face_512)
        original_face_128 = t128(original_face_256)
        #cv2.imwrite('test.png', cv2.cvtColor(original_face_512.permute(1,2,0).cpu().numpy(), cv2.COLOR_RGB2BGR))

        if swapper_model == 'Inswapper128':
            latent = torch.from_numpy(self.models.calc_swapper_latent(s_e)).float().to('cuda')
            if parameters['FaceLikenessSwitch']:
                factor = parameters['FaceLikenessFactorSlider']
                dst_latent = torch.from_numpy(self.models.calc_swapper_latent(t_e)).float().to('cuda')            
                latent = latent - (factor * dst_latent)
            
            dim = 1
            if parameters['SwapperTypeTextSel'] == '128':
                dim = 1
                input_face_affined = original_face_128
            elif parameters['SwapperTypeTextSel'] == '256':
                dim = 2
                input_face_affined = original_face_256
            elif parameters['SwapperTypeTextSel'] == '512':
                dim = 4
                input_face_affined = original_face_512
        elif swapper_model == 'SimSwap512':
            latent = torch.from_numpy(self.models.calc_swapper_latent_simswap512(s_e)).float().to('cuda')
            if parameters['FaceLikenessSwitch']:
                factor = parameters['FaceLikenessFactorSlider']
                dst_latent = torch.from_numpy(self.models.calc_swapper_latent_simswap512(t_e)).float().to('cuda')
                latent = latent - (factor * dst_latent)

            dim = 4
            input_face_affined = original_face_512
        elif swapper_model == 'GF1' or swapper_model == 'GF2' or swapper_model == 'GF3':
            latent = torch.from_numpy(self.models.calc_swapper_latent_ghost(s_e)).float().to('cuda')
            if parameters['FaceLikenessSwitch']:
                factor = parameters['FaceLikenessFactorSlider']
                dst_latent = torch.from_numpy(self.models.calc_swapper_latent_ghost(t_e)).float().to('cuda')
                latent = latent - (factor * dst_latent)

            dim = 2
            input_face_affined = original_face_256

        # Optional Scaling # change the thransform matrix
        if parameters['FaceAdjSwitch']:
            #input_face_affined = v2.functional.affine(input_face_affined, 0, (0, 0), 1 + parameters['FaceScaleSlider'] / 100, 0, center=(dim*128-1, dim*128-1), interpolation=v2.InterpolationMode.BILINEAR)
            input_face_affined = v2.functional.affine(input_face_affined, 0, (0, 0), 1 + parameters['FaceScaleSlider'] / 100, 0, center=(dim*128/2, dim*128/2), interpolation=v2.InterpolationMode.BILINEAR)

        itex = 1
        if parameters['StrengthSwitch']:
            itex = ceil(parameters['StrengthSlider'] / 100.)

        output_size = int(128 * dim)
        output = torch.zeros((output_size, output_size, 3), dtype=torch.float32, device='cuda')
        input_face_affined = input_face_affined.permute(1, 2, 0)
        input_face_affined = torch.div(input_face_affined, 255.0)

        if swapper_model == 'Inswapper128':
            for k in range(itex):
                for j in range(dim):
                    for i in range(dim):
                        input_face_disc = input_face_affined[j::dim,i::dim]
                        input_face_disc = input_face_disc.permute(2, 0, 1)
                        input_face_disc = torch.unsqueeze(input_face_disc, 0).contiguous()

                        swapper_output = torch.empty((1,3,128,128), dtype=torch.float32, device='cuda').contiguous()
                        self.models.run_swapper(input_face_disc, latent, swapper_output)

                        swapper_output = torch.squeeze(swapper_output)
                        swapper_output = swapper_output.permute(1, 2, 0)


                        output[j::dim, i::dim] = swapper_output.clone()
                prev_face = input_face_affined.clone()
                input_face_affined = output.clone()
                output = torch.mul(output, 255)
                output = torch.clamp(output, 0, 255)

        elif swapper_model == 'SimSwap512':
            for k in range(itex):
                input_face_disc = input_face_affined.permute(2, 0, 1)
                input_face_disc = torch.unsqueeze(input_face_disc, 0).contiguous()
                swapper_output = torch.empty((1,3,512,512), dtype=torch.float32, device='cuda').contiguous()
                self.models.run_swapper_simswap512(input_face_disc, latent, swapper_output)
                swapper_output = torch.squeeze(swapper_output)
                swapper_output = swapper_output.permute(1, 2, 0)
                prev_face = input_face_affined.clone()
                input_face_affined = swapper_output.clone()

                output = swapper_output.clone()
                output = torch.mul(output, 255)
                output = torch.clamp(output, 0, 255)

        elif swapper_model == 'GF1' or swapper_model == 'GF2' or swapper_model == 'GF3':
            for k in range(itex):
                input_face_disc = torch.mul(input_face_affined, 255.0).permute(2, 0, 1)
                input_face_disc = torch.div(input_face_disc.float(), 127.5)
                input_face_disc = torch.sub(input_face_disc, 1)
                #input_face_disc = input_face_disc[[2, 1, 0], :, :] # Inverte i canali da BGR a RGB (assumendo che l'input sia BGR)
                input_face_disc = torch.unsqueeze(input_face_disc, 0).contiguous()
                swapper_output = torch.empty((1,3,256,256), dtype=torch.float32, device='cuda').contiguous()
                self.models.run_swapper_ghostface(input_face_disc, latent, swapper_output, swapper_model)
                swapper_output = swapper_output[0]
                swapper_output = swapper_output.permute(1, 2, 0)
                swapper_output = torch.mul(swapper_output, 127.5)
                swapper_output = torch.add(swapper_output, 127.5)
                #swapper_output = swapper_output[:, :, [2, 1, 0]] # Inverte i canali da RGB a BGR (assumendo che l'input sia RGB)
                prev_face = input_face_affined.clone()
                input_face_affined = swapper_output.clone()
                input_face_affined = torch.div(input_face_affined, 255)

                output = swapper_output.clone()
                output = torch.clamp(output, 0, 255)
                #cv2.imwrite('test_swap.png', cv2.cvtColor(output.cpu().numpy(), cv2.COLOR_RGB2BGR))

        output = output.permute(2, 0, 1)

        swap = t512(output)
        #cv2.imwrite('test_swap512.png', cv2.cvtColor(swap.permute(1,2,0).cpu().numpy(), cv2.COLOR_RGB2BGR))

        if parameters['StrengthSwitch']:
            if itex == 0:
                swap = original_face_512.clone()
            else:
                alpha = np.mod(parameters['StrengthSlider'], 100)*0.01
                if alpha==0:
                    alpha=1

                # Blend the images
                prev_face = torch.mul(prev_face, 255)
                prev_face = torch.clamp(prev_face, 0, 255)
                prev_face = prev_face.permute(2, 0, 1)
                prev_face = t512(prev_face)
                swap = torch.mul(swap, alpha)
                prev_face = torch.mul(prev_face, 1-alpha)
                swap = torch.add(swap, prev_face)




            # swap = torch.squeeze(swap)
            # swap = torch.mul(swap, 255)
            # swap = torch.clamp(swap, 0, 255)
            # # swap_128 = swap
            # swap = t256(swap)
            # swap = t512(swap)

        # Create border mask
        border_mask = torch.ones((128, 128), dtype=torch.float32, device=device)
        border_mask = torch.unsqueeze(border_mask,0)
        
        # if parameters['BorderState']:
        top = parameters['BorderTopSlider']
        left = parameters['BorderLeftSlider']
        right = 128-parameters['BorderRightSlider']
        bottom = 128-parameters['BorderBottomSlider']

        border_mask[:, :top, :] = 0
        border_mask[:, bottom:, :] = 0
        border_mask[:, :, :left] = 0
        border_mask[:, :, right:] = 0

        gauss = transforms.GaussianBlur(parameters['BorderBlurSlider']*2+1, (parameters['BorderBlurSlider']+1)*0.2)
        border_mask = gauss(border_mask)        

        # Create image mask
        swap_mask = torch.ones((128, 128), dtype=torch.float32, device=device)
        swap_mask = torch.unsqueeze(swap_mask,0)    

        # Face Diffing
        if parameters["DiffSwitch"]:
            mask = self.apply_fake_diff(swap, original_face_512, parameters["DiffSlider"])
            # mask = t128(mask)
            gauss = transforms.GaussianBlur(parameters['BlendSlider']*2+1, (parameters['BlendSlider']+1)*0.2)
            mask = gauss(mask.type(torch.float32)) 
            swap = swap*mask + original_face_512*(1-mask)
 
        # Restorer
        if parameters["RestorerSwitch"]: 
            swap = self.func_w_test('Restorer', self.apply_restorer, swap, parameters)  

        # Apply color corerctions
        if parameters['ColorSwitch']:
            # print(parameters['ColorGammaSlider'])
            swap = torch.unsqueeze(swap,0).contiguous()
            swap = v2.functional.adjust_gamma(swap, parameters['ColorGammaSlider'], 1.0)
            swap = torch.squeeze(swap)
            swap = swap.permute(1, 2, 0).type(torch.float32)

            del_color = torch.tensor([parameters['ColorRedSlider'], parameters['ColorGreenSlider'], parameters['ColorBlueSlider']], device=device)
            swap += del_color                 
            swap = torch.clamp(swap, min=0., max=255.)
            swap = swap.permute(2, 0, 1).type(torch.uint8)    

            swap = v2.functional.adjust_brightness(swap, parameters['ColorBrightSlider'])
            swap = v2.functional.adjust_contrast(swap, parameters['ColorContrastSlider'])
            swap = v2.functional.adjust_saturation(swap, parameters['ColorSaturationSlider'])
            swap = v2.functional.adjust_sharpness(swap, parameters['ColorSharpnessSlider'])
            swap = v2.functional.adjust_hue(swap, parameters['ColorHueSlider'])
            
        # Occluder
        if parameters["OccluderSwitch"]:
            mask = self.func_w_test('occluder', self.apply_occlusion , original_face_256, parameters["OccluderSlider"])
            mask = t128(mask)  
            swap_mask = torch.mul(swap_mask, mask)

        if parameters["DFLXSegSwitch"]:
            img_mask = self.func_w_test('occluder', self.apply_dfl_xseg , original_face_256, -parameters["DFLXSegSlider"])
            img_mask = t128(img_mask)
            swap_mask = torch.mul(swap_mask, 1 - img_mask)

        if parameters["FaceParserSwitch"]:
            mask = self.apply_face_parser(swap, parameters)
            mask = t128(mask)
            swap_mask = torch.mul(swap_mask, mask)            
        
        # CLIPs 
        if parameters["CLIPSwitch"]:
            with lock:
                mask = self.func_w_test('CLIP', self.apply_CLIPs, original_face_512, parameters["CLIPTextEntry"], parameters["CLIPSlider"])
            mask = cv2.resize(mask, (128,128))
            mask = torch.from_numpy(mask).to('cuda')
            swap_mask *= mask


        # Add blur to swap_mask results
        gauss = transforms.GaussianBlur(parameters['BlendSlider']*2+1, (parameters['BlendSlider']+1)*0.2)
        swap_mask = gauss(swap_mask)
        #cv2.imwrite('test_swap512_2.png', cv2.cvtColor(swap.permute(1,2,0).cpu().numpy(), cv2.COLOR_RGB2BGR))

        # Combine border and swap mask, scale, and apply to swap
        swap_mask = torch.mul(swap_mask, border_mask)
        swap_mask = t512(swap_mask)
        swap = torch.mul(swap, swap_mask)

        if not control['MaskViewButton']:
            # Cslculate the area to be mergerd back to the original frame
            IM512 = tform.inverse.params[0:2, :]
            corners = np.array([[0,0], [0,511], [511, 0], [511, 511]])

            x = (IM512[0][0]*corners[:,0] + IM512[0][1]*corners[:,1] + IM512[0][2])
            y = (IM512[1][0]*corners[:,0] + IM512[1][1]*corners[:,1] + IM512[1][2])
            
            left = floor(np.min(x))
            if left<0:
                left=0
            top = floor(np.min(y))
            if top<0: 
                top=0
            right = ceil(np.max(x))
            if right>img.shape[2]:
                right=img.shape[2]            
            bottom = ceil(np.max(y))
            if bottom>img.shape[1]:
                bottom=img.shape[1]   

            # Untransform the swap
            swap = v2.functional.pad(swap, (0,0,img.shape[2]-512, img.shape[1]-512))
            swap = v2.functional.affine(swap, tform.inverse.rotation*57.2958, (tform.inverse.translation[0], tform.inverse.translation[1]), tform.inverse.scale, 0,interpolation=v2.InterpolationMode.BILINEAR, center = (0,0) )
            swap = swap[0:3, top:bottom, left:right]
            swap = swap.permute(1, 2, 0)
            #cv2.imwrite('test_swap512_3.png', cv2.cvtColor(swap.cpu().numpy(), cv2.COLOR_RGB2BGR))

            # Untransform the swap mask
            swap_mask = v2.functional.pad(swap_mask, (0,0,img.shape[2]-512, img.shape[1]-512))
            swap_mask = v2.functional.affine(swap_mask, tform.inverse.rotation*57.2958, (tform.inverse.translation[0], tform.inverse.translation[1]), tform.inverse.scale, 0, interpolation=v2.InterpolationMode.BILINEAR, center = (0,0) )
            swap_mask = swap_mask[0:1, top:bottom, left:right]                        
            swap_mask = swap_mask.permute(1, 2, 0)
            swap_mask = torch.sub(1, swap_mask) 

            # Apply the mask to the original image areas
            img_crop = img[0:3, top:bottom, left:right]
            img_crop = img_crop.permute(1,2,0)            
            img_crop = torch.mul(swap_mask,img_crop)
            
            #Add the cropped areas and place them back into the original image
            swap = torch.add(swap, img_crop)
            swap = swap.type(torch.uint8)
            swap = swap.permute(2,0,1)
            img[0:3, top:bottom, left:right] = swap
            #cv2.imwrite('test_swap512_4.png', cv2.cvtColor(img.permute(1,2,0).cpu().numpy(), cv2.COLOR_RGB2BGR))

        else:
            # Invert swap mask
            swap_mask = torch.sub(1, swap_mask)
            
            # Combine preswapped face with swap
            original_face_512 = torch.mul(swap_mask, original_face_512)
            original_face_512 = torch.add(swap, original_face_512)            
            original_face_512 = original_face_512.type(torch.uint8)
            original_face_512 = original_face_512.permute(1, 2, 0)

            # Uninvert and create image from swap mask
            swap_mask = torch.sub(1, swap_mask) 
            swap_mask = torch.cat((swap_mask,swap_mask,swap_mask),0)
            swap_mask = swap_mask.permute(1, 2, 0)

            # Place them side by side
            img = torch.hstack([original_face_512, swap_mask*255])
            img = img.permute(2,0,1)

        return img

    # @profile    
    def apply_occlusion(self, img, amount):        
        img = torch.div(img, 255)
        img = torch.unsqueeze(img, 0).contiguous()
        outpred = torch.ones((256,256), dtype=torch.float32, device=device).contiguous()
        
        self.models.run_occluder(img, outpred)        
                
        outpred = torch.squeeze(outpred)
        outpred = (outpred > 0)
        outpred = torch.unsqueeze(outpred, 0).type(torch.float32)
        
        if amount >0:                   
            kernel = torch.ones((1,1,3,3), dtype=torch.float32, device=device)

            for i in range(int(amount)):
                outpred = torch.nn.functional.conv2d(outpred, kernel, padding=(1, 1))       
                outpred = torch.clamp(outpred, 0, 1)
            
            outpred = torch.squeeze(outpred)
            
        if amount <0:      
            outpred = torch.neg(outpred)
            outpred = torch.add(outpred, 1)
            kernel = torch.ones((1,1,3,3), dtype=torch.float32, device=device)

            for i in range(int(-amount)):
                outpred = torch.nn.functional.conv2d(outpred, kernel, padding=(1, 1))       
                outpred = torch.clamp(outpred, 0, 1)
            
            outpred = torch.squeeze(outpred)
            outpred = torch.neg(outpred)
            outpred = torch.add(outpred, 1)
            
        outpred = torch.reshape(outpred, (1, 256, 256)) 
        return outpred

    def apply_dfl_xseg(self, img, amount):
        img = img.type(torch.float32)
        img = torch.div(img, 255)
        img = torch.unsqueeze(img, 0).contiguous()
        outpred = torch.ones((256,256), dtype=torch.float32, device=device).contiguous()
        
        self.models.run_dfl_xseg(img, outpred)
        
        outpred = torch.clamp(outpred, min=0.0, max=1.0)
        outpred[outpred < 0.1] = 0
        # invert values to mask areas to keep
        outpred = 1.0 - outpred
        outpred = torch.unsqueeze(outpred, 0).type(torch.float32)

        if amount > 0:                   
            kernel = torch.ones((1,1,3,3), dtype=torch.float32, device=device)

            for i in range(int(amount)):
                outpred = torch.nn.functional.conv2d(outpred, kernel, padding=(1, 1))       
                outpred = torch.clamp(outpred, 0, 1)
            
            outpred = torch.squeeze(outpred)
            
        if amount < 0:      
            outpred = torch.neg(outpred)
            outpred = torch.add(outpred, 1)
            kernel = torch.ones((1,1,3,3), dtype=torch.float32, device=device)

            for i in range(int(-amount)):
                outpred = torch.nn.functional.conv2d(outpred, kernel, padding=(1, 1))       
                outpred = torch.clamp(outpred, 0, 1)
            
            outpred = torch.squeeze(outpred)
            outpred = torch.neg(outpred)
            outpred = torch.add(outpred, 1)
            
        outpred = torch.reshape(outpred, (1, 256, 256)) 
        return outpred
      
    def apply_CLIPs(self, img, CLIPText, CLIPAmount):
        clip_mask = np.ones((352, 352))
        img = img.permute(1,2,0)
        img = img.cpu().numpy()
        # img = img.to(torch.float)
        # img = img.permute(1,2,0)
        transform = transforms.Compose([transforms.ToTensor(),
                                        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]), 
                                        transforms.Resize((352, 352))])
        CLIPimg = transform(img).unsqueeze(0).contiguous()
        
        if CLIPText != "":
            prompts = CLIPText.split(',')

            with torch.no_grad():
                preds = self.clip_session(CLIPimg.repeat(len(prompts),1,1,1), prompts)[0]
                # preds = self.clip_session(CLIPimg,  maskimg, True)[0]

            clip_mask = 1 - torch.sigmoid(preds[0][0])
            for i in range(len(prompts)-1):
                clip_mask *= 1-torch.sigmoid(preds[i+1][0])
            clip_mask = clip_mask.data.cpu().numpy()
            
            thresh = CLIPAmount/100.0
            clip_mask[clip_mask>thresh] = 1.0
            clip_mask[clip_mask<=thresh] = 0.0
        return clip_mask   
     
    # @profile
    def apply_face_parser(self, img, parameters):

        # atts = [1 'skin', 2 'l_brow', 3 'r_brow', 4 'l_eye', 5 'r_eye', 6 'eye_g', 7 'l_ear', 8 'r_ear', 9 'ear_r', 10 'nose', 11 'mouth', 12 'u_lip', 13 'l_lip', 14 'neck', 15 'neck_l', 16 'cloth', 17 'hair', 18 'hat']
        FaceAmount = parameters["FaceParserSlider"]
        outpred = torch.ones((512,512), dtype=torch.float32, device='cuda').contiguous()
        

        img = torch.div(img, 255)
        img = v2.functional.normalize(img, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
        img = torch.reshape(img, (1, 3, 512, 512))
        outpred = torch.empty((1,19,512,512), dtype=torch.float32, device='cuda').contiguous()

        self.models.run_faceparser(img, outpred)

        outpred = torch.squeeze(outpred)
        outpred = torch.argmax(outpred, 0)

        face_attributes = {
            2: parameters['LeftEyeBrowParserSlider'], #Left Eyebrow
            3: parameters['RightEyeBrowParserSlider'], #Right Eyebrow
            4: parameters['LeftEyeParserSlider'], #Left Eye
            5: parameters['RightEyeParserSlider'], #Right Eye
            10: parameters['NoseParserSlider'], #Nose
            11: parameters['MouthParserSlider'], #Mouth
            12: parameters['UpperLipParserSlider'], #Upper Lip
            13: parameters['LowerLipParserSlider'], #Lower Lip
            14: parameters['NeckParserSlider'], #Neck
        }
        face_parses = []
        for attribute in face_attributes.keys():
            if face_attributes[attribute] > 0:
                attribute_idxs = torch.tensor( [attribute], device='cuda')
                iters = int(face_attributes[attribute])

                attribute_parse = torch.isin(outpred, attribute_idxs)
                attribute_parse = torch.clamp(~attribute_parse, 0, 1).type(torch.float32)
                attribute_parse = torch.reshape(attribute_parse, (1,1,512,512))
                attribute_parse = torch.neg(attribute_parse)
                attribute_parse = torch.add(attribute_parse, 1)

                kernel = torch.ones((1,1,3,3), dtype=torch.float32, device='cuda')

                for i in range(iters):
                    attribute_parse = torch.nn.functional.conv2d(attribute_parse, kernel, padding=(1, 1))
                    attribute_parse = torch.clamp(attribute_parse, 0, 1)

                attribute_parse = torch.squeeze(attribute_parse)
                attribute_parse = torch.neg(attribute_parse)
                attribute_parse = torch.add(attribute_parse, 1)
                attribute_parse = torch.reshape(attribute_parse, (1, 512, 512))
            else:
                attribute_parse = torch.ones((1, 512, 512), dtype=torch.float32, device='cuda')
            face_parses.append(attribute_parse)


        # BG Parse
        bg_idxs = torch.tensor([0, 14, 15, 16, 17, 18], device=device)
        bg_parse = torch.isin(outpred, bg_idxs)
        bg_parse = torch.clamp(~bg_parse, 0, 1).type(torch.float32)
        bg_parse = torch.reshape(bg_parse, (1, 1, 512, 512))

        if FaceAmount > 0:
            kernel = torch.ones((1, 1, 3, 3), dtype=torch.float32, device=device)

            for i in range(int(FaceAmount)):
                bg_parse = torch.nn.functional.conv2d(bg_parse, kernel, padding=(1, 1))
                bg_parse = torch.clamp(bg_parse, 0, 1)

            bg_parse = torch.squeeze(bg_parse)

        elif FaceAmount < 0:
            bg_parse = torch.neg(bg_parse)
            bg_parse = torch.add(bg_parse, 1)

            kernel = torch.ones((1, 1, 3, 3), dtype=torch.float32, device=device)

            for i in range(int(-FaceAmount)):
                bg_parse = torch.nn.functional.conv2d(bg_parse, kernel, padding=(1, 1))
                bg_parse = torch.clamp(bg_parse, 0, 1)

            bg_parse = torch.squeeze(bg_parse)
            bg_parse = torch.neg(bg_parse)
            bg_parse = torch.add(bg_parse, 1)
            bg_parse = torch.reshape(bg_parse, (1, 512, 512))
        else:
            bg_parse = torch.ones((1,512,512), dtype=torch.float32, device='cuda')

        out_parse = bg_parse
        for face_parse in face_parses:
            out_parse = torch.mul(out_parse, face_parse)
        # out_parse = torch.mul(out_parse, left_eye_parse)
        return out_parse

    def apply_bg_face_parser(self, img, FaceParserAmount):

        # atts = [1 'skin', 2 'l_brow', 3 'r_brow', 4 'l_eye', 5 'r_eye', 6 'eye_g', 7 'l_ear', 8 'r_ear', 9 'ear_r', 10 'nose', 11 'mouth', 12 'u_lip', 13 'l_lip', 14 'neck', 15 'neck_l', 16 'cloth', 17 'hair', 18 'hat']
        # out = np.ones((512, 512), dtype=np.float32)  
        
        outpred = torch.ones((512,512), dtype=torch.float32, device='cuda').contiguous()

        # turn mouth parser off at 0 so someone can just use the mouth parser
        if FaceParserAmount != 0:
            img = torch.div(img, 255)
            img = v2.functional.normalize(img, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
            img = torch.reshape(img, (1, 3, 512, 512))      
            outpred = torch.empty((1,19,512,512), dtype=torch.float32, device=device).contiguous()

            self.models.run_faceparser(img, outpred)

            outpred = torch.squeeze(outpred)
            outpred = torch.argmax(outpred, 0)

            test = torch.tensor([ 0, 14, 15, 16, 17, 18], device=device)
            outpred = torch.isin(outpred, test)
            outpred = torch.clamp(~outpred, 0, 1).type(torch.float32)
            outpred = torch.reshape(outpred, (1,1,512,512))
            
            if FaceParserAmount >0:                   
                kernel = torch.ones((1,1,3,3), dtype=torch.float32, device=device)

                for i in range(int(FaceParserAmount)):
                    outpred = torch.nn.functional.conv2d(outpred, kernel, padding=(1, 1))
                    outpred = torch.clamp(outpred, 0, 1)
                
                outpred = torch.squeeze(outpred)
                
            if FaceParserAmount <0:      
                outpred = torch.neg(outpred)
                outpred = torch.add(outpred, 1)

                kernel = torch.ones((1,1,3,3), dtype=torch.float32, device=device)

                for i in range(int(-FaceParserAmount)):
                    outpred = torch.nn.functional.conv2d(outpred, kernel, padding=(1, 1))
                    outpred = torch.clamp(outpred, 0, 1)
                
                outpred = torch.squeeze(outpred)
                outpred = torch.neg(outpred)
                outpred = torch.add(outpred, 1)

        outpred = torch.reshape(outpred, (1, 512, 512))
        
        return outpred
    

        
    def apply_restorer(self, swapped_face_upscaled, parameters):     
        temp = swapped_face_upscaled
        t512 = v2.Resize((512, 512), antialias=False)
        t256 = v2.Resize((256, 256), antialias=False)
        t1024 = v2.Resize((1024, 1024), antialias=False)
        t2048 = v2.Resize((2048, 2048), antialias=False)

        # If using a separate detection mode
        if parameters['RestorerDetTypeTextSel'] == 'Blend' or parameters['RestorerDetTypeTextSel'] == 'Reference':
            if parameters['RestorerDetTypeTextSel'] == 'Blend':
                # Set up Transformation
                dst = self.arcface_dst * 4.0
                dst[:,0] += 32.0        

            elif parameters['RestorerDetTypeTextSel'] == 'Reference':
                try:
                    dst = self.models.resnet50(swapped_face_upscaled, score=parameters['DetectScoreSlider']/100.0) 
                except:
                    return swapped_face_upscaled       
            
            tform = trans.SimilarityTransform()
            tform.estimate(dst, self.FFHQ_kps)

            # Transform, scale, and normalize
            temp = v2.functional.affine(swapped_face_upscaled, tform.rotation*57.2958, (tform.translation[0], tform.translation[1]) , tform.scale, 0, center = (0,0) )
            temp = v2.functional.crop(temp, 0,0, 512, 512)        
        
        temp = torch.div(temp, 255)
        temp = v2.functional.normalize(temp, (0.5, 0.5, 0.5), (0.5, 0.5, 0.5), inplace=False)
        if parameters['RestorerTypeTextSel'] == 'GP256':
            temp = t256(temp)
        temp = torch.unsqueeze(temp, 0).contiguous()

        # Bindings
        outpred = torch.empty((1,3,512,512), dtype=torch.float32, device=device).contiguous()

        if parameters['RestorerTypeTextSel'] == 'GFPGAN':
            self.models.run_GFPGAN(temp, outpred)            
            
        elif parameters['RestorerTypeTextSel'] == 'CF':
            self.models.run_codeformer(temp, outpred) 
            
        elif parameters['RestorerTypeTextSel'] == 'GP256':
            outpred = torch.empty((1,3,256,256), dtype=torch.float32, device=device).contiguous()
            self.models.run_GPEN_256(temp, outpred) 
            
        elif parameters['RestorerTypeTextSel'] == 'GP512':
            self.models.run_GPEN_512(temp, outpred) 

        elif parameters['RestorerTypeTextSel'] == 'GP1024':
            temp = t1024(temp)
            outpred = torch.empty((1, 3, 1024, 1024), dtype=torch.float32, device=device).contiguous()
            self.models.run_GPEN_1024(temp, outpred)

        elif parameters['RestorerTypeTextSel'] == 'GP2048':
            temp = t2048(temp)
            outpred = torch.empty((1, 3, 2048, 2048), dtype=torch.float32, device=device).contiguous()
            self.models.run_GPEN_2048(temp, outpred)

        # Format back to cxHxW @ 255
        outpred = torch.squeeze(outpred)      
        outpred = torch.clamp(outpred, -1, 1)
        outpred = torch.add(outpred, 1)
        outpred = torch.div(outpred, 2)
        outpred = torch.mul(outpred, 255)
        if parameters['RestorerTypeTextSel'] == 'GP256' or parameters['RestorerTypeTextSel'] == 'GP1024' or parameters['RestorerTypeTextSel'] == 'GP2048':
            outpred = t512(outpred)
        # Invert Transform
        if parameters['RestorerDetTypeTextSel'] == 'Blend' or parameters['RestorerDetTypeTextSel'] == 'Reference':
            outpred = v2.functional.affine(outpred, tform.inverse.rotation*57.2958, (tform.inverse.translation[0], tform.inverse.translation[1]), tform.inverse.scale, 0, interpolation=v2.InterpolationMode.BILINEAR, center = (0,0) )

        # Blend
        alpha = float(parameters["RestorerSlider"])/100.0  
        outpred = torch.add(torch.mul(outpred, alpha), torch.mul(swapped_face_upscaled, 1-alpha))

        return outpred        
        
    def apply_fake_diff(self, swapped_face, original_face, DiffAmount):
        swapped_face = swapped_face.permute(1,2,0)
        original_face = original_face.permute(1,2,0)

        diff = swapped_face-original_face
        diff = torch.abs(diff)
        
        # Find the diffrence between the swap and original, per channel
        fthresh = DiffAmount*2.55
        
        # Bimodal
        diff[diff<fthresh] = 0
        diff[diff>=fthresh] = 1 
        
        # If any of the channels exceeded the threshhold, them add them to the mask
        diff = torch.sum(diff, dim=2)
        diff = torch.unsqueeze(diff, 2)
        diff[diff>0] = 1
        
        diff = diff.permute(2,0,1)

        return diff    
    
    
    def clear_mem(self):
        del self.swapper_model
        del self.GFPGAN_model
        del self.occluder_model
        del self.face_parsing_model
        del self.codeformer_model
        del self.GPEN_256_model
        del self.GPEN_512_model
        del self.GPEN_1024_model
        del self.resnet_model
        del self.detection_model
        del self.recognition_model
        
        self.swapper_model = []  
        self.GFPGAN_model = []
        self.occluder_model = []
        self.face_parsing_model = []
        self.codeformer_model = []
        self.GPEN_256_model = []
        self.GPEN_512_model = []
        self.GPEN_1024_model = []
        self.resnet_model = []
        self.detection_model = []
        self.recognition_model = []

        # test = swap.permute(1, 2, 0)
        # test = test.cpu().numpy()
        # cv2.imwrite('2.jpg', test) 


    def soft_circular_mask(self, height, width, center, radius, feather_radius):
        """
        Create a soft circular mask with feathering effect.

        Args:
            height (int): Height of the mask.
            width (int): Width of the mask.
            center (tuple): Center of the circle (x, y).
            radius (int): Radius of the circle.
            feather_radius (int): Radius for feathering effect.

        Returns:
            torch.Tensor: Soft circular mask tensor of shape (H, W).
        """
        y, x = torch.meshgrid(torch.arange(height), torch.arange(width), indexing='ij')
        distance = torch.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2)
        mask = torch.clamp((radius - distance) / feather_radius, 0, 1)
        return mask

    def restore_mouth(self, img_orig, img_swap, kpss_orig, blend_alpha=0.5, feather_radius=10, size_factor=0.5):
        """
        Extract mouth from img_orig using the provided keypoints and place it in img_swap.

        Args:
            img_orig (torch.Tensor): The original image tensor of shape (C, H, W) from which mouth is extracted.
            img_swap (torch.Tensor): The target image tensor of shape (C, H, W) where mouth is placed.
            kpss_orig (list): List of keypoints arrays for detected faces. Each keypoints array contains coordinates for 5 keypoints.

        Returns:
            torch.Tensor: The resulting image tensor with mouth from img_orig placed on img_swap.
        """
        left_mouth = np.array([int(val) for val in kpss_orig[3]])
        right_mouth = np.array([int(val) for val in kpss_orig[4]])

        mouth_center = (left_mouth + right_mouth) // 2
        mouth_radius = int(np.linalg.norm(left_mouth - right_mouth) * size_factor)

        ymin = max(0, mouth_center[1] - mouth_radius)
        ymax = min(img_orig.size(1), mouth_center[1] + mouth_radius)
        xmin = max(0, mouth_center[0] - mouth_radius)
        xmax = min(img_orig.size(2), mouth_center[0] + mouth_radius)

        mouth_region_orig = img_orig[:, ymin:ymax, xmin:xmax]
        mouth_mask = self.soft_circular_mask(ymax - ymin, xmax - xmin, (mouth_radius, mouth_radius), mouth_radius, feather_radius).to(img_orig.device)

        target_ymin = ymin
        target_ymax = ymin + mouth_region_orig.size(1)
        target_xmin = xmin
        target_xmax = xmin + mouth_region_orig.size(2)

        img_swap_mouth = img_swap[:, target_ymin:target_ymax, target_xmin:target_xmax]
        blended_mouth = blend_alpha * img_swap_mouth + (1 - blend_alpha) * mouth_region_orig

        img_swap[:, target_ymin:target_ymax, target_xmin:target_xmax] = mouth_mask * blended_mouth + (1 - mouth_mask) * img_swap_mouth
        return img_swap

    def restore_eyes(self, img_orig, img_swap, kpss_orig, blend_alpha=0.5, feather_radius=10, size_factor=3.5):
        """
        Extract eyes from img_orig using the provided keypoints and place them in img_swap.

        Args:
            img_orig (torch.Tensor): The original image tensor of shape (C, H, W) from which eyes are extracted.
            img_swap (torch.Tensor): The target image tensor of shape (C, H, W) where eyes are placed.
            kpss_orig (list): List of keypoints arrays for detected faces. Each keypoints array contains coordinates for 5 keypoints.

        Returns:
            torch.Tensor: The resulting image tensor with eyes from img_orig placed on img_swap.
        """
        left_eye = np.array([int(val) for val in kpss_orig[0]])
        right_eye = np.array([int(val) for val in kpss_orig[1]])

        eye_distance = np.linalg.norm(left_eye - right_eye)
        eye_radius = int(eye_distance / size_factor)

        def extract_and_blend_eye(eye_center, eye_radius, img_orig, img_swap, blend_alpha, feather_radius):
            ymin = max(0, eye_center[1] - eye_radius)
            ymax = min(img_orig.size(1), eye_center[1] + eye_radius)
            xmin = max(0, eye_center[0] - eye_radius)
            xmax = min(img_orig.size(2), eye_center[0] + eye_radius)

            eye_region_orig = img_orig[:, ymin:ymax, xmin:xmax]
            eye_mask = self.soft_circular_mask(ymax - ymin, xmax - xmin, (eye_radius, eye_radius), eye_radius, feather_radius).to(img_orig.device)

            target_ymin = ymin
            target_ymax = ymin + eye_region_orig.size(1)
            target_xmin = xmin
            target_xmax = xmin + eye_region_orig.size(2)

            img_swap_eye = img_swap[:, target_ymin:target_ymax, target_xmin:target_xmax]
            blended_eye = blend_alpha * img_swap_eye + (1 - blend_alpha) * eye_region_orig

            img_swap[:, target_ymin:target_ymax, target_xmin:target_xmax] = eye_mask * blended_eye + (1 - eye_mask) * img_swap_eye

        extract_and_blend_eye(left_eye, eye_radius, img_orig, img_swap, blend_alpha, feather_radius)
        extract_and_blend_eye(right_eye, eye_radius, img_orig, img_swap, blend_alpha, feather_radius)

        return img_swap