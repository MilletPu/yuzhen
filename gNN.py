# coding=utf-8

import obspy
import numpy as np
import pandas as pd
import csv
import datetime
import math
import os

# CUDA_VISIBLE_DEVICES = "0"  # 使用第4块GPU显卡
CUDA_VISIBLE_DEVICES = ""  # 使用CPU
os.environ["CUDA_VISIBLE_DEVICES"] = CUDA_VISIBLE_DEVICES
from keras.optimizers import SGD
from keras.models import Sequential
from keras.layers import Dense
from keras.utils import to_categorical

from obspy.signal.trigger import plot_trigger
from obspy.signal.trigger import recursive_sta_lta
from obspy.signal.trigger import trigger_onset
from obspy.signal.trigger import classic_sta_lta
from obspy.signal.trigger import delayed_sta_lta
from obspy.signal.filter import *
from preprocessing import *


# original testing data
def windowedTestingData(sac, point, preSize=10, postSize=20):
    pre = sac.data[point + 1 - preSize: point + 1]
    post = sac.data[point + 1: point + 1 + postSize]
    testingSeq = np.concatenate([pre, post])
    return testingSeq


# MINMAX testing data
def windowedMinMaxTestingData(sac, point, preSize=10, postSize=20):
    pre = sac.data[point + 1 - preSize: point + 1]
    post = sac.data[point + 1: point + 1 + postSize]
    testingSeq = np.concatenate([pre, post])
    if len(testingSeq) != 0:
        testingSeq = minMaxScale(testingSeq, range=(-100, 100))
    return np.array(testingSeq)


# Inputa a sac and get the on_of array. pujun 10 1000
def getTrigger(sac, short=2, long=25):  # 1.75 1.25 4.wan perfect
    df = sac.stats.sampling_rate
    # print 'sampling_rate = '
    # print df
    # get cft
    cft = recursive_sta_lta(sac.data, int(short * df), int(long * df))
    # set threshold
    threshold = np.mean(cft) + (np.max(cft) - np.mean(cft)) / 4
    if np.isnan(threshold) == 1:
        print 'thre = nan'
        threshold = 3.2
    # get on
    # gk change
    # on_of = trigger_onset(cft, threshold, threshold)
    on_of = trigger_onset(cft, threshold * 1.38, threshold * 0.92)
    if len(on_of) != 0:
        return on_of[:, 0]
    else:
        return np.array([])


def trainNN():
    # POSITIVE training data
    posPX, posSX = getAllWindowedMinMaxPositiveTrainingData('./sample/example30', preSize=10, postSize=20)
    posPY = np.array([[1]] * len(posPX))
    posSY = np.array([[1]] * len(posSX))

    # NEGATIVE training data
    negX = getSomeWindowedMinMaxNegativeTrainingData('./sample/example30/', size=30, num=200)
    negY = np.array([[0]] * 200)

    # ALL training data
    X = np.concatenate([posPX, posSX, negX])
    Y = np.concatenate([posPY, posSY, negY])

    # 使用keras创建神经网络
    # Sequential是指一层层堆叠的神经网络
    # Dense是指全连接层
    # 定义model
    model = Sequential()
    model.add(Dense(50, input_dim=30, activation='sigmoid'))
    model.add(Dense(50, activation='sigmoid'))
    model.add(Dense(10, activation='sigmoid'))
    model.add(Dense(1, activation='sigmoid'))
    model.compile(loss='binary_crossentropy', optimizer='rmsprop', metrics=['accuracy'])
    # model.compile(loss='categorical_crossentropy', optimizer='sgd', metrics=['accuracy'])
    model.fit(X, Y, epochs=200, batch_size=32)
    model.save('model.h5')
    return model


# VAR-AIC  after lta/sta use   change by gk
def var_aic(sac, point, preSize=1200, postSize=1200):
    i = 20

    aic = 100000
    minnum = 0
    k = np.array(sac.data[point + 1 - preSize: point + 1 + postSize])
    # print k
    re = []
    for d1 in k:
        if i > (postSize + preSize - 100):
            break
        # print '(np.var(k[0:i])) =',(np.var(k[0:i])),np.var(k[i:1999])
        k1 = np.var(k[0:i])
        k2 = np.var(k[i:1999])
        if k1 == 0 or k2 == 0:
            continue
        ak = i * math.log10(k1) + (preSize + postSize - i) * (math.log10(k2))
        re.append(ak)
        if ak < aic:
            aic = ak
            minnum = i
        i += 1
    # plot(re)
    # print 'minnum = ',point -1200 +minnum
    return point - 1200 + minnum


def predictOneSacSaved(sacDir):
    res = []
    sac = readOneSac(sacDir)
    # dai tong lv bo
    tr_filt = sac.copy()
    tr_filt.filter('bandpass', freqmin=8, freqmax=18, corners=4, zerophase=False)
    # t = np.arange(0, sac.stats.npts / sac.stats.sampling_rate, sac.stats.delta)
    # plt.subplot(211)
    # plt.plot(sac, sac.data, 'k')
    # plt.ylabel('Raw Data')
    # plt.subplot(212)
    # plt.plot(t, tr_filt.data, 'k')
    # plt.ylabel('Lowpassed Data')
    # plt.xlabel('Time [s]')
    # plt.suptitle(sac.stats.starttime)
    # plt.show()
    ti = sac.stats.starttime
    ti_unix = float(ti.strftime("%s.%f"))

    triggers = getTrigger(tr_filt)
    if len(triggers) != 0:
        i = 1
        b = 0.1
        for point in triggers:

            testingSeq = windowedMinMaxTestingData(tr_filt, point)
            prob = model.predict(testingSeq.reshape(1, -1))
            if prob > 0.0000000001:

                aicpoint = var_aic(tr_filt, point)
                time = round(float(aicpoint) / 100.00, 2)  # round(a/b,2)
                print 'new point = ', round(float(point) / 100.00, 2) - round(float(aicpoint) / 100.00, 2)

                time_submission = float(
                    datetime.datetime.fromtimestamp(ti_unix + 8 * 3600 + time).strftime('%Y%m%d%H%M%S.%f'))
                if i % 2 == 1:
                    wave_type = 'P'
                    i += 1
                else:
                    if point - b < 300:
                        print point - b
                        continue
                    if point - b > 25000:
                        wave_type = 'p'
                        i += 1
                    else:
                        wave_type = 's'
                        i = 1
                if abs(round(float(point) / 100.00, 2) - round(float(aicpoint) / 100.00, 2)) < 6:
                    res.append([sac.stats.station, time_submission, wave_type])
                    b = point
                i += 1
    return res


if __name__ == '__main__':

    starttime = datetime.datetime.now()
    csvfile = file('31goodv_result.csv', 'wb')
    writer = csv.writer(csvfile)
    # writer.writerow(['Station', 'Time', 'Type'])

    model = trainNN()
    dirs = ['./preliminary/after']
    for dir in dirs:
        pathDirBefore = os.listdir(dir)
        for eachFile in pathDirBefore:
            eachFile = os.path.join('%s/%s' % (dir, eachFile))
            print eachFile
            res_one = predictOneSacSaved(eachFile)
            writer.writerows(res_one)

    csvfile.close()

    endtime = datetime.datetime.now()
    print "Spend time:"
    print endtime - starttime
