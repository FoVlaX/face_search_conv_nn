from keras import backend as K
import time
from multiprocessing.dummy import Pool
import pickle
K.set_image_data_format('channels_first')
import cv2
import os
import copy
import glob
import numpy as np
from numpy import genfromtxt
import tensorflow as tf
from fr_utils import *
from inception_blocks_v2 import *
import win32com.client as wincl
from vk_loader import load_photos_from_vk
import random
import shutil

PADDING = 0
ready_to_detect_identity = True
windows10_voice_interface = wincl.Dispatch("SAPI.SpVoice")

FRmodel = faceRecoModel(input_shape=(3, 96, 96))


def triplet_loss(y_true, y_pred, alpha=0.3):
    """
    Implementation of the triplet loss as defined by formula (3)

    Arguments:
    y_pred -- python list containing three objects:
            anchor -- the encodings for the anchor images, of shape (None, 128)
            positive -- the encodings for the positive images, of shape (None, 128)
            negative -- the encodings for the negative images, of shape (None, 128)

    Returns:
    loss -- real number, value of the loss
    """

    anchor, positive, negative = y_pred[0], y_pred[1], y_pred[2]

    # Step 1: Compute the (encoding) distance between the anchor and the positive, you will need to sum over axis=-1
    pos_dist = tf.reduce_sum(tf.square(tf.subtract(anchor, positive)), axis=-1)
    # Step 2: Compute the (encoding) distance between the anchor and the negative, you will need to sum over axis=-1
    neg_dist = tf.reduce_sum(tf.square(tf.subtract(anchor, negative)), axis=-1)
    # Step 3: subtract the two previous distances and add alpha.
    basic_loss = tf.add(tf.subtract(pos_dist, neg_dist), alpha)
    # Step 4: Take the maximum of basic_loss and 0.0. Sum over the training examples.
    loss = tf.reduce_sum(tf.maximum(basic_loss, 0.0))

    return loss


FRmodel.compile(optimizer='adam', loss=triplet_loss, metrics=['accuracy'])
load_weights_from_FaceNet(FRmodel)


def save_obj(obj, name ):
    with open('obj/'+ name + '.pkl', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_obj(name ):
    with open('obj/' + name + '.pkl', 'rb') as f:
        return pickle.load(f)

def prepare_database():

    database = {}
    database_name = "vk_database"
    try:
        database = load_obj(database_name)
    except:
        database = {}

    # load all the images of individuals to recognize into the database
    for file in glob.glob("images/*"):
        identity = os.path.splitext(os.path.basename(file))[0]
        database[identity] = img_path_to_encoding(file, FRmodel)
    try:
        save_obj(database, database_name)
    except:
        pass

    return database

database = {}

def load_local_vk_database():
    global database
    database_name = "vk_database"
    try:
        database = load_obj(database_name)
    except:
        database = {}
    return database

def prepare_database_from_vk(face_cascade):
    global database
    database_name = "vk_database"
    try:
        database = load_obj(database_name)
    except:
        database = {}
    def add_photo_to_database(identity, image):
        global database
        nparr = np.fromstring(image, np.uint8)
        img_np = cv2.imdecode(nparr, 1)
        find_faces_and_add_to_db(img_np, database, identity, face_cascade)
    # load all the images of individuals to recognize into the database
    load_photos_from_vk(0, 100, add_photo_to_database)

    try:
        save_obj(database, database_name)
    except Exception as ex:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(ex).__name__, ex.args)
        print(message)

    return database

def find_faces_and_add_to_db(image,database,identity, face_cascade):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    # Loop through all the faces detected and determine whether or not they are in the database
    for (x, y, w, h) in faces:
        x1 = x - PADDING
        y1 = y - PADDING
        x2 = x + w + PADDING
        y2 = y + h + PADDING
        height, width, channels = image.shape
        # The padding is necessary since the OpenCV face detector creates the bounding box around the face and not the head
        part_image = image[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]
        ident = str(x+w/2)+'_'+str(y+h/2)+'_face_'+str(identity)
        database[ident] = img_to_encoding(part_image, FRmodel)
        new_image = copy.copy(image)
        cv2.rectangle(new_image, (x1, y1), (x2, y2), (255, 0, 0), 2)
        cv2.imwrite('output_images/'+ident.replace('/','_')+'.png', new_image)
        print(ident)

def webcam_face_recognizer(database):
    """
    Runs a loop that extracts images from the computer's webcam and determines whether or not
    it contains the face of a person in our database.
    If it contains a face, an audio message will be played welcoming the user.
    If not, the program will process the next frame from the webcam
    """
    global ready_to_detect_identity

    cv2.namedWindow("preview")
    vc = cv2.VideoCapture(0)

    face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

    while vc.isOpened():
        _, frame = vc.read()
        img = frame

        # We do not want to detect a new identity while the program is in the process of identifying another person
        if ready_to_detect_identity:
            img = process_frame(img, frame, face_cascade)

        key = cv2.waitKey(100)
        cv2.imshow("preview", img)

        if key == 27:  # exit on ESC
            break
    cv2.destroyWindow("preview")

def who_is_on_photo(image_path, face_cascade):
    img1 = cv2.imread(image_path, 1)
    #img1 = cv2.resize(img1, (256, 256))
    return process_frame(img1, img1, face_cascade)

def process_frame(img, frame, face_cascade):
    """
    Determine whether the current frame contains the faces of people from our database
    """
    global ready_to_detect_identity
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    # Loop through all the faces detected and determine whether or not they are in the database
    identities = []
    for (x, y, w, h) in faces:
        x1 = x - PADDING
        y1 = y - PADDING
        x2 = x + w + PADDING
        y2 = y + h + PADDING

        img = cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

        identity = find_identity(frame, x1, y1, x2, y2)

        if identity is not None:
            identities.append(identity)

    if identities != []:
        cv2.imwrite('example.png', img)
    return img, identities


def find_identity(frame, x1, y1, x2, y2):
    """
    Determine whether the face contained within the bounding box exists in our database
    x1,y1_____________
    |                 |
    |                 |
    |_________________x2,y2
    """
    height, width, channels = frame.shape
    # The padding is necessary since the OpenCV face detector creates the bounding box around the face and not the head
    part_image = frame[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]

    return who_is_it(part_image, database, FRmodel)


def who_is_it(image, database, model):
    """
    Implements face recognition for the happy house by finding who is the person on the image_path image.

    Arguments:
    image_path -- path to an image
    database -- database containing image encodings along with the name of the person on the image
    model -- your Inception model instance in Keras

    Returns:
    min_dist -- the minimum distance between image_path encoding and the encodings from the database
    identity -- string, the name prediction for the person on image_path
    """
    encoding = img_to_encoding(image, model)

    min_dist = 100
    identity = None
    identities = []
    # Loop over the database dictionary's names and encodings.
    for (name, db_enc) in database.items():

        # Compute L2 distance between the target "encoding" and the current "emb" from the database.
        dist = np.linalg.norm(encoding - db_enc)

        print('distance for %s is %s' % (name, dist))
        identities.append((name, dist))
        # If this distance is less than the min_dist, then set min_dist to dist, and identity to name
        if dist < min_dist:
            min_dist = dist
            identity = name

    identities = sorted(identities, key=lambda identity: identity[1])

    return identities[:5]


def welcome_users(identities):
    """ Outputs a welcome audio message to the users """
    global ready_to_detect_identity
    welcome_message = 'Welcome '

    if len(identities) == 1:
        welcome_message += '%s, have a nice day.' % identities[0]
    else:
        for identity_id in range(len(identities) - 1):
            welcome_message += '%s, ' % identities[identity_id]
        welcome_message += 'and %s, ' % identities[-1]
        welcome_message += 'have a nice day!'

    windows10_voice_interface.Speak(welcome_message)

    # Allow the program to start detecting identities again
    ready_to_detect_identity = True


def clastering(database, count):
    lst = list(database.keys())
    print(lst)
    clasters = []
    random.shuffle(lst)
    for number in range(count):
        clasters.append(
            database[lst[number]]
        )
    dic = {  }
    for x in range(30):
        dic, clasters = bind_to_claster(database, clasters)
    print(dic)

    for key, value in dic.items():
        try:
            os.makedirs("class" + str(value+1))
        except:
            pass

        shutil.copyfile("output_images/"+key.replace("/","_") + ".png", "class"+str(value+1)+"/"+key.replace("/","_") +".png")



def bind_to_claster(database, clasters):

    dic = {}

    for key, value in database.items():
        min_dist = 22
        min_index = 0
        ind = 0
        for cl in clasters:
            dist = np.linalg.norm(value - cl)
            if dist < min_dist:
                min_index = ind
                min_dist = dist
            ind = ind + 1
        dic[key] = min_index

    #calculate new clasters

    for number in range(len(clasters)):
        claster_list = list(filter(lambda it: it[1] == number, dic.items()))
        if (len(claster_list) > 0):
            Sum = database[claster_list[0][0]]
            for item in claster_list:
                Sum = Sum + database[item[0]]
            Sum = Sum / len(claster_list)
            clasters[number] = Sum

    return dic, clasters


if __name__ == "__main__":
    face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
    #database = prepare_database_from_vk(face_cascade)
    database = load_local_vk_database()
    #print(database)
    #webcam_face_recognizer(database)
    _, identities = who_is_on_photo(
        image_path="images/testimage.jpg",
        face_cascade=face_cascade
    )
    print(identities)
    #   database=database,
    #   count=9
    #)

