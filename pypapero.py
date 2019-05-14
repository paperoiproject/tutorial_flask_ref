# -*- coding:utf-8 -*-
##############################################################
# PaPeRo i 制御用ライブラリ(Ver.1.01)
# Copyright (c) 2016 Sophia Planning Inc. All Rights Reserved
# ライセンス：MIT
##############################################################
# 更新履歴
# 2017/10/16(Ver.1.01)
#   ・WebSocket通信終了処理の変更
#   ・通信スレッドの廃止
#
# 2016/09/21(Ver.1.00)
#   ・startSpeechコマンド送信関数の不具合修正、引数追加
#
# 2016/08/02(β版)
#   ・stopFaceDetectionコマンドが正しく送信されない不具合を修正
#
# 2016/06/15(β版)
#   ・SSL対応
#   ・汎用モーション関連コマンド送信関数追加
#   ・takePicture/deleteCaptureDataコマンド送信関数追加
#   ・デフォルトではログ出力しないよう変更
#
# 2016/05/30(β版)
#   ・録音・再生関連コマンド送信関数追加
#
# 2016/05/25(β版)
#   ・初版公開
##############################################################
from logging import getLogger, debug, info, warn, error, critical
logger = getLogger(__name__)

import threading
import json
import queue
import time
import math

from ws4py.client.threadedclient import WebSocketClient


class PaperoClient(WebSocketClient):
    """
    WebSocketのイベントハンドラクラス
    """

    def opened(self):
        """
        回線接続時の処理
        """
        self.papero.wsAvail = True
        logger.debug("-------------------")
        logger.debug("connected")
        logger.debug("--------------------")

    def closed(self, code, reason):
        """
        回線切断時の処理
        """
        if self.papero is not None:
            self.papero.wsAvail = False
            self.papero.queFromCom.put(None)
            self.papero = None
        logger.debug("-------------------")
        logger.debug("disconnected")
        logger.debug("--------------------")

    def received_message(self, msgrcv):
        """
        伝文受信時の処理
        """
        message = str(msgrcv)
        logger.debug("received:" + message)
        self.papero.queFromCom.put(message)


def get_now_time_for_robot_message():
    """
    ロボット伝文送信の為の時刻取得
    """
    t = time.localtime()
    str_yyyy = str(t.tm_year)
    str_mth = ("0" + str(t.tm_mon))[-2:]
    str_day = ("0" + str(t.tm_mday))[-2:]
    str_hh = ("0" + str(t.tm_hour))[-2:]
    str_mm = ("0" + str(t.tm_min))[-2:]
    str_ss = ("0" + str(t.tm_sec))[-2:]
    return str_yyyy + "-" + str_mth + "-" + str_day + " " + str_hh + ":" + str_mm + ":" + str_ss


def set_common_for_command(msg_dic_snd, msg_name, msg_dst):
    """
    ロボット制御コマンド共通項目設定
    """
    msg_dic_snd["Name"] = msg_name
    msg_dic_snd["Type"] = "Command"
    msg_dic_snd["Destination"] = msg_dst
    msg_dic_snd["Source"] = "Script"
    msg_dic_snd["Time"] = get_now_time_for_robot_message()


def build_seq_str(list_seq, n_limit):
    """
    Motor・LED関連コマンド用シーケンス文字列組み立て
    """
    n = min(len(list_seq), n_limit)
    rtn_str = ""
    for i in range(n):
        if rtn_str != "":
            rtn_str += ","
        rtn_str += list_seq[i]
    return rtn_str


class Papero:
    """
    Paperoクラス
    """

    def __init__(self, simulator_id, robot_name, arg_ws_server_addr):
        """
        @param simulator_id:シミュレータID
        @param robot_name:ロボット名
        @param arg_ws_server_addr:WebSocket接続先(""ならデフォルトの接続先)
        """
        ws_server_addr = "wss://smilerobo.com:8000/papero"  # デフォルトの接続先
        if arg_ws_server_addr != "":
            ws_server_addr = arg_ws_server_addr
        logger.debug("simulator_id=" + str(simulator_id))
        logger.debug("robot_name=" + str(robot_name))
        logger.debug("ws_server_addr=" + str(ws_server_addr))
        self.simulatorID = simulator_id
        self.robotName = robot_name
        self.robotID = 0
        self.messageID = 0
        self.errOccurred = 0
        self.errDetail = ""
        self.scriptMayFinish = False
        # WebSocket関連
        self.wsAvail = False
        # self.ws = PaperoClient(ws_server_addr, protocols=['http-only'])
        self.ws = PaperoClient(ws_server_addr, protocols=None)
        self.ws.papero = self
        self.ws.connect()
        # スレッド間通信用キュー
        self.queFromCom = queue.Queue()
        # Ver.1.01 発話コマンド個数管理
        self.remain_speech_count = 0
        self.papero_init()

    def papero_init(self):
        """
        パペロ初期化
        """
        while not self.wsAvail:
            time.sleep(0.1)
        self.send_select_sim_robot()
        while True:
            message = self.papero_recv(None)
            if message is not None:
                msg_dic_rcv = json.loads(message)
                if msg_dic_rcv["Name"] == "Ready":
                    self.robotID = msg_dic_rcv["RobotID"]
                    break
                elif msg_dic_rcv["Name"] == "Error":
                    logger.error("------Received error (papero_init()). Detail : " + msg_dic_rcv["Detail"])
                    self.papero_send(None)
                    self.errOccurred = 1
                    self.errDetail = "Inithalize failed"
                    break
            elif self.errOccurred != 0:
                logger.error("------Error occurred(papero_init()). Detail : " + self.errDetail)
                self.papero_send(None)
                self.errDetail = "Inithalize failed"
                break

    def papero_send(self, msg_dic_snd):
        """
        伝文送信
        @param msg_dic_snd:送信するJSON文字列(Noneを設定すると通信終了となる)
        """
        if self.ws is not None:
            if msg_dic_snd is None:
                self.scriptMayFinish = True
                self.ws.close()
                past_time = 0.0
                delta_time = 0.1
                st = 0
                while self.wsAvail and (self.errOccurred == 0) and (st >= 0):
                    messages = self.papero_robot_message_recv(delta_time)
                    if st == 0:
                        if (self.remain_speech_count <= 0) or (past_time > 5.0):
                            st = 1
                        else:
                            past_time += delta_time
                    elif st == 1:
                        if messages is None:
                            st = (-1)
                self.wsAvail = False
                self.ws = None
            else:
                msg_json_snd = json.dumps(msg_dic_snd)
                self.ws.send(msg_json_snd)
                logger.debug("sending:" + msg_json_snd)

    def send_select_sim_robot(self):
        """
        シミュレータ・ロボット選択送信
        """
        msg_dic_snd = {}
        msg_dic_snd["Name"] = "SelectSimRobot"
        msg_dic_snd["SimulatorID"] = self.simulatorID
        msg_dic_snd["RobotName"] = self.robotName
        self.papero_send(msg_dic_snd)

    def send_robot_message(self, message):
        """
        ロボット伝文送信
        """
        msg_dic_snd = {}
        msg_dic_snd["Name"] = "RobotMessage"
        msg_dic_snd["RobotID"] = self.robotID
        msg_dic_snd["Messages"] = [message]
        self.papero_send(msg_dic_snd)

    def send_script_end(self):
        """
        スクリプト終了送信
        """
        msg_dic_snd = {}
        msg_dic_snd["Name"] = "ScriptEnd"
        msg_dic_snd["RobotID"] = self.robotID
        self.papero_send(msg_dic_snd)

    def send_script_abort(self):
        """
        スクリプト異常終了送信
        """
        msg_dic_snd = {}
        msg_dic_snd["Name"] = "ScriptAbort"
        msg_dic_snd["RobotID"] = self.robotID
        self.papero_send(msg_dic_snd)

    def send_move_head(self, vertical, horizontal, repeat=False, priority="normal"):
        """
        moveHeadコマンド送信
        @param vertical:上下パラメータシーケンス(パターンのリスト)
        @param horizontal:水平パラメータシーケンス(パターンのリスト)
        @param repeat:繰り返しの有無(True又はFalse)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        if repeat:
            str_repeat = "true"
        else:
            str_repeat = "false"
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "moveHead", "MotorController")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["VerticalSequence"] = str(min(len(vertical), 64))
        msg_dic_snd["HorizontalSequence"] = str(min(len(horizontal), 64))
        msg_dic_snd["Repeat"] = str_repeat
        msg_dic_snd["Vertical"] = build_seq_str(vertical, 64)
        msg_dic_snd["Horizontal"] = build_seq_str(horizontal, 64)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_head(self, priority="normal"):
        """
        stopHeadコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopHead", "MotorController")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_reset_head(self, priority="normal"):
        """
        resetHeadコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return 戻り値:messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "resetHead", "MotorController")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_head_status(self, priority="normal"):
        """
        getHeadStatusコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return 戻り値:messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getHeadStatus", "MotorController")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_turn_led_on(self, part, pattern, repeat=False, priority="normal"):
        """
        turnLedOnコマンド送信
        @param part:"ear"、"forehead"、"cheek"、"mouth"、"chest"のいずれか
        @param pattern:パターン
        @param repeat:"true"、"false"のいずれか
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        if repeat:
            str_repeat = "true"
        else:
            str_repeat = "false"
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "turnLedOn", "LEDController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Part"] = part
        msg_dic_snd["Sequence"] = str(min(math.floor(len(pattern) / 2), 26))
        msg_dic_snd["Repeat"] = str_repeat
        msg_dic_snd["Pattern"] = build_seq_str(pattern, 26 * 2)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_turn_led_off(self, part, priority="normal"):
        """
        turnLedOffコマンド送信
        @param part:"ear"、"forehead"、"cheek"、"mouth"、"chest"のいずれか
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "turnLedOff", "LEDController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Part"] = part
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_set_default_status_led(self, status, priority="normal"):
        """
        setDefaultStatusコマンド送信(LED)
        @param status:設定する輝度
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "setDefaultStatus", "LEDController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Target"] = "Luminance"
        msg_dic_snd["Status"] = status
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_default_status_led(self, priority="normal"):
        """
        getDefaultStatusコマンド送信(LED)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getDefaultStatus", "LEDController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Target"] = "Luminance"
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_led_status(self, part, priority="normal"):
        """
        getLedStatusコマンド送信
        @param part:"ear"、"forehead"、"cheek"、"mouth"、"chest"のいずれか
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getLedStatus", "LEDController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Part"] = part
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_speech(self, text,
                          language=None, speaker_id=None,
                          pitch=None, speed=None, volume=None,
                          pause=None, comma_pause=None, urgent=None, priority="normal"):
        """
        startSpeechコマンド送信
        @param text:読み上げ対象テキスト
        @param language:言語
        @param speaker_id:話者ID
        @param pitch:高程高低
        @param speed:発話速度
        @param volume:発話音量
        @param pause:文章間ポーズ時間
        @param comma_pause:カンマのポーズ時間
        @param urgent:音声カテゴリ
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startSpeech", "SpeechSynthesizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Text"] = text
        if language is not None:
            msg_dic_snd["Language"] = str(language)
        if speaker_id is not None:
            msg_dic_snd["SpeakerID"] = str(speaker_id)
        if pitch is not None:
            msg_dic_snd["Pitch"] = str(pitch)
        if speed is not None:
            msg_dic_snd["Speed"] = str(speed)
        if volume is not None:
            msg_dic_snd["Volume"] = str(volume)
        if pause is not None:
            msg_dic_snd["Pause"] = str(pause)
        if comma_pause is not None:
            msg_dic_snd["CommaPause"] = str(comma_pause)
        if urgent is not None:
            msg_dic_snd["Urgent"] = str(urgent)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        self.remain_speech_count += 1 # Ver.1.01 発話コマンド個数管理
        return msg_dic_snd["MessageID"]

    def send_pause_speech(self, priority="normal"):
        """
        pauseSpeechコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "pauseSpeech", "SpeechSynthesizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_resume_speech(self, priority="normal"):
        """
        resumeSpeechコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "resumeSpeech", "SpeechSynthesizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_speech(self, priority="normal"):
        """
        stopSpeechコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopSpeech", "SpeechSynthesizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_speech_status(self, priority="normal"):
        """
        getSpeechStatusコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getSpeechStatus", "SpeechSynthesizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_set_default_status_speech(self, language="0", speaker_id="3",
                                       pitch="100", speed="100", volume="100",
                                       pause="800", comma_pause="300",
                                       priority="normal"):
        """
        setDefaultStatusコマンド送信(Speech)
        @param language:言語
        @param speaker_id:話者ID
        @param pitch:高程高低
        @param speed:発話速度
        @param volume:発話音量
        @param pause:文章間ポーズ時間
        @param comma_pause:カンマのポーズ時間
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "setDefaultStatus", "SpeechSynthesizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Language"] = str(language)
        msg_dic_snd["SpeakerID"] = str(speaker_id)
        msg_dic_snd["Pitch"] = str(pitch)
        msg_dic_snd["Speed"] = str(speed)
        msg_dic_snd["Volume"] = str(volume)
        msg_dic_snd["Pause"] = str(pause)
        msg_dic_snd["CommaPause"] = str(comma_pause)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_default_status_speech(self, priority="normal"):
        """
        getDefaultStatusコマンド送信(Speech)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getDefaultStatus", "SpeechSynthesizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_sensor_value(self, priority="normal"):
        """
        getSensorValueコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getSensorValue", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_acc_sensor(self, priority="normal"):
        """
        startAccSensorコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startAccSensor", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_acc_sensor(self, priority="normal"):
        """
        stopAccSensorコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopAccSensor", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_set_acc_sensor(self, mem_size, full_scale, data_rate, priority="normal"):
        """
        setAccSensorコマンド送信
        @param mem_size:Queバッファメモリサイズ(1000～1200)
        @param full_scale:0:±2g , 1:±4g , 2:±8g , 3:±16g
        @param data_rate:2:10Hz、3:25Hz、4:50Hz、5:100Hz、9:1344Hz
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "setAccSensor", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["MemSize"] = str(mem_size)
        msg_dic_snd["FullScale"] = str(full_scale)
        msg_dic_snd["DataRate"] = str(data_rate)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_acc_sensor_state(self, priority="normal"):
        """
        getAccSensorStateコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getAccSensorState", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_set_acc_sensor_threshold(self, det_value, los_value, frequency, arg_time, priority="normal"):
        """
        setAccSensorThresholdコマンド送信
        @param det_value:揺れ開始閾値
        @param los_value:揺れ終了閾値
        @param frequency:揺れ開始閾値を超える回数
        @param arg_time:揺れ終了閾値が連続して閾値を下回る期間
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "setAccSensorThreshold", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["DetValue"] = str(det_value)
        msg_dic_snd["LosValue"] = str(los_value)
        msg_dic_snd["Frequency"] = str(frequency)
        msg_dic_snd["Time"] = str(arg_time)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_lum_sensor(self, priority="normal"):
        """
        startLumSensorコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startLumSensor", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_lum_sensor(self, priority="normal"):
        """
        stopLumSensorコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopLumSensor", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_lum_sensor_value(self, priority="normal"):
        """
        getLumSensorValueコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getLumSensorValue", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_lum_sensor_state(self, priority="normal"):
        """
        getLumSensorStateコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getLumSensorState", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_cancel_command(self, target_id, priority="normal"):
        """
        cancelCommandコマンド送信
        @param target_id:キャンセルするメッセージID
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getSensorValue", "SensorController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["TargetID"] = target_id
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_speech_recognition(self, priority="normal"):
        """
        startSpeechRecognitionコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startSpeechRecognition", "SpeechRecognizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_speech_recognition(self, priority="normal"):
        """
        stopSpeechRecognitionコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopSpeechRecognition", "SpeechRecognizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_speech_recognition_status(self, priority="normal"):
        """
        getSpeechRecognitionStatusコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getSpeechRecognitionStatus", "SpeechRecognizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_read_dictionary(self, mrg_file_name, priority="normal"):
        """
        readDictionaryコマンド送信
        @param mrg_file_name:辞書ファイルパス名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "readDictionary", "SpeechRecognizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["MrgFileName"] = mrg_file_name
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_free_dictionary(self, mrg_file_name, priority="normal"):
        """
        freeDictionaryコマンド送信
        @param mrg_file_name:辞書ファイルパス名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "freeDictionary", "SpeechRecognizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["MrgFileName"] = mrg_file_name
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_add_speech_recognition_rule(self, rule_name, priority="normal"):
        """
        addSpeechRecognitionRuleコマンド送信
        @param rule_name:ルール名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "addSpeechRecognitionRule", "SpeechRecognizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["RuleName"] = rule_name
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_delete_speech_recognition_rule(self, rule_name, priority="normal"):
        """
        deleteSpeechRecognitionRuleコマンド送信
        @param rule_name:ルール名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "deleteSpeechRecognitionRule", "SpeechRecognizer")
        msg_dic_snd["Expiration"] = "120"
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["RuleName"] = rule_name
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_take_picture(self, format, filename=None, camera=None, priority="normal"):
        """
        takePictureコマンド送信
        @param format:"RGB"、"JPEG"のいずれか
        @param filename:ファイル名(省略可)
        @param camera:"VGA"/"SXGA"(指定しない場合はNone)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "takePicture", "VideoCapture")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Format"] = str(format)
        if filename is not None:
            msg_dic_snd["Filename"] = str(filename)
        if camera is not None:
            msg_dic_snd["Camera"] = str(camera)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_delete_capture_data(self, filename, priority="normal"):
        """
        deleteCaptureDataコマンド送信
        @param filename:ファイル名
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "deleteCaptureData", "VideoCapture")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        msg_dic_snd["Filename"] = str(filename)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_capturing(self, share_mem_id, share_mem_size, camera, priority="normal"):
        """
        startCapturingコマンド送信
        @param priority:優先度("higher"又は"normal")
        @param share_mem_id:共有メモリID(指定しない場合はNone)
        @param share_mem_size:共有メモリサイズ
        @param camera:"VGA"/"XGA"(指定しない場合はNone)
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startCapturing", "CameraController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        if share_mem_id is not None:
            msg_dic_snd["ShareMemID"] = str(share_mem_id)
        msg_dic_snd["ShareMemSize"] = str(share_mem_size)
        if camera is not None:
            msg_dic_snd["Camera"] = str(camera)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_capturing(self, share_mem_id, camera, priority="normal"):
        """
        stopCapturingコマンド送信
        @param priority:優先度("higher"又は"normal")
        @param share_mem_id:共有メモリID(指定しない場合はNone)
        @param camera:"VGA"/"SXGA"(指定しない場合はNone)
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopCapturing", "CameraController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        if share_mem_id is not None:
            msg_dic_snd["ShareMemID"] = str(share_mem_id)
        if camera is not None:
            msg_dic_snd["Camera"] = str(camera)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_capture_data(self, share_mem_id, camera, priority="normal"):
        """
        getCaptureDataコマンド送信
        @param priority:優先度("higher"又は"normal")
        @param share_mem_id:共有メモリID(指定しない場合はNone)
        @param camera:"VGA"/"XGA"(指定しない場合はNone)
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getCaptureData", "CameraController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        if share_mem_id is not None:
            msg_dic_snd["ShareMemID"] = str(share_mem_id)
        if camera is not None:
            msg_dic_snd["Camera"] = str(camera)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_set_camera_status(self, brightness=None, contrast=None,
                               hue=None, saturation=None,
                               sharpness=None, gamma=None, white_balance=None,
                               auto_white_balance=None, iris=None,
                               camera=None, priority="normal"):
        """
        setCameraStatusコマンド送信
        @param brightness:明るさ
        @param contrast:コントラスト
        @param hue:色相、色合い
        @param saturation:彩度、鮮やかさ
        @param sharpness:シャープネス、鮮明度
        @param gamma:ガンマ補正
        @param white_balance:ホワイトバランス
        @param auto_white_balance:自動ホワイトバランス
        @param iris:虹彩
        @param camera:"VGA"/"SXGA"
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "setCameraStatus", "VideoCapture")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        if brightness is not None:
            msg_dic_snd["Brightness"] = str(brightness)
        if contrast is not None:
            msg_dic_snd["Contrast"] = str(contrast)
        if hue is not None:
            msg_dic_snd["Hue"] = str(hue)
        if saturation is not None:
            msg_dic_snd["Saturation"] = str(saturation)
        if sharpness is not None:
            msg_dic_snd["Sharpness"] = sharpness
        if gamma is not None:
            msg_dic_snd["Gamma"] = gamma
        if white_balance is not None:
            msg_dic_snd["WhiteBalance"] = white_balance
        if auto_white_balance is not None:
            msg_dic_snd["AutoWhiteBalance"] = auto_white_balance
        if iris is not None:
            msg_dic_snd["Iris"] = iris
        if camera is not None:
            msg_dic_snd["Camera"] = str(camera)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_camera_status(self, object, camera, priority="normal"):
        """
        getCameraStatusコマンド送信
        @param object:取得するプロパティ名(Noneを指定すると全取得となる)
        @param camera:"VGA"/"SXGA"(指定しない場合はNone)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getCameraStatus", "VideoCapture")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        if object is not None:
            msg_dic_snd["Object"] = str(object)
        if camera is not None:
            msg_dic_snd["Camera"] = str(camera)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_one_shot_capture_data(self, share_mem_id, share_mem_size,
                                       camera, priority="normal"):
        """
        getOneShotCaptureData コマンド送信
        @param priority:優先度("higher"又は"normal")
        @param share_mem_id:共有メモリID
        @param share_mem_size:共有メモリサイズ
        @param camera:"VGA"/"XGA"(指定しない場合はNone)
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getOneShotCaptureData", "CameraController")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        if share_mem_id is not None:
            msg_dic_snd["ShareMemID"] = str(share_mem_id)
        msg_dic_snd["ShareMemSize"] = str(share_mem_size)
        if camera is not None:
            msg_dic_snd["Camera"] = str(camera)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_face_detection(self, min_eye_distance, priority="normal"):
        """
        startFaceDetectionコマンド送信
        @param priority:優先度("higher"又は"normal")
        @param min_eye_distance:最小目間距離(指定しない場合はNone)
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startFaceDetection", "FaceDetection")
        msg_dic_snd["Priority"] = priority
        if min_eye_distance is not None:
            msg_dic_snd["MinEyeDistance"] = str(min_eye_distance)
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_face_detection(self, priority="normal"):
        """
        stopFaceDetectionコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopFaceDetection", "FaceDetection")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_recording(self, filename=None, bitlength=None, bitrate=None,
                             channel="Monaural", recordingtime=None, priority="normal"):
        """
        startRecordingコマンド送信
        @param bitlength:1サンプルのビット長
        @param bitrate:ビットレート
        @param channel:"Monaural"、"Stereo"のいずれか
        @param filename:ファイル名
        @param recordingtime:録音時間(秒)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startRecording", "WaveRecorder")
        msg_dic_snd["Storage"] = "File"
        if filename is not None:
            msg_dic_snd["Filename"] = filename
        if bitlength is not None:
            msg_dic_snd["BitLength"] = str(bitlength)
        if bitrate is not None:
            msg_dic_snd["Bitrate"] = str(bitrate)
        if channel is not None:
            msg_dic_snd["Channel"] = channel
        msg_dic_snd["Format"] = "Wav"
        if recordingtime is not None:
            msg_dic_snd["RecordingTime"] = str(recordingtime)
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_recording(self, priority="normal"):
        """
        stopRecordingコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopRecording", "WaveRecorder")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_delete_recording_data(self, filename, priority="normal"):
        """
        deleteRecordingDataコマンド送信
        @param filename:削除対象ファイル名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "deleteRecordingData", "WaveRecorder")
        msg_dic_snd["Filename"] = filename
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_recording_status(self, priority="normal"):
        """
        getRecordingStatusコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getRecordingStatus", "WaveRecorder")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_set_default_status_wavrec(self, bitrate=None, channel=None,
                                       bitlength=None, recordingtime=None,
                                       priority="normal"):
        """
        setDefaultStatusコマンド送信(録音)
        @param bitrate:ビットレート
        @param channel:"Monaural"、"Stereo"のいずれか
        @param bitlength:1サンプルのビット長
        @param recordingtime:録音時間(秒)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "setDefaultStatus", "WaveRecorder")
        if bitrate is not None:
            msg_dic_snd["Bitrate"] = bitrate
        if channel is not None:
            msg_dic_snd["Channel"] = channel
        if bitlength is not None:
            msg_dic_snd["BitLength"] = str(bitlength)
        if recordingtime is not None:
            msg_dic_snd["RecordingTime"] = str(recordingtime)
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_default_status_wavrec(self, object, priority="normal"):
        """
        getDefaultStatusコマンド送信(録音)
        @param object:取得するプロパティ名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getDefaultStatus", "WaveRecorder")
        msg_dic_snd["Object"] = object
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_playing(self, filename, volume=None, category=1, priority="normal"):
        """
        startPlayingコマンド送信
        @param filename:再生ファイル名
        @param volume:音量(1～10、0の場合はデフォルト値を使用)
        @param category:再生モード(1:通常時、2:緊急時)
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startPlaying", "WavePlayer")
        msg_dic_snd["Filename"] = filename
        if volume is not None:
            msg_dic_snd["Volume"] = str(volume)
        msg_dic_snd["Category"] = str(category)
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_playing(self, priority="normal"):
        """
        stopPlayingコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopPlaying", "WavePlayer")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_delete_wave_data(self, filename, priority="normal"):
        """
        deleteWaveDataコマンド送信
        @param filename:削除対象ファイル名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "deleteWaveData", "WavePlayer")
        msg_dic_snd["Filename"] = filename
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_playing_status(self, priority="normal"):
        """
        getPlayingStatusコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getPlayingStatus", "WavePlayer")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_set_default_status_wavplay(self, volume, priority="normal"):
        """
        setDefaultStatusコマンド送信(再生)
        @param volume:ボリューム
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "setDefaultStatus", "WavePlayer")
        msg_dic_snd["Volume"] = volume
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_get_default_status_wavplay(self, object, priority="normal"):
        """
        getDefaultStatusコマンド送信(録音)
        @param object:取得するプロパティ名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "getDefaultStatus", "WavePlayer")
        msg_dic_snd["Object"] = object
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_start_motion(self, motion_id, sound="None", text=None, priority="normal"):
        """
        startMotionコマンド送信
        @param motion_id:モーションID(1～19)
        @param sound:"None"、"Japanese"、"Plan"のいずれか
        @param text:sound="Japanese"の場合は発話テキスト、sound="Play"の場合はwavファイル名
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "startMotion", "SystemManager")
        msg_dic_snd["Motion"] = "00000000"
        msg_dic_snd["Argv1"] = ("00000000" + str(motion_id))[-8:]
        msg_dic_snd["Argv2"] = sound
        argc = 3
        if sound == "None":
            argc = 2
        else:
            msg_dic_snd["Argv3"] = text
        msg_dic_snd["Argc"] = str(argc)
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def send_stop_motion(self, priority="normal"):
        """
        startMotionコマンド送信
        @param priority:優先度("higher"又は"normal")
        @return messageID
        """
        msg_dic_snd = {}
        set_common_for_command(msg_dic_snd, "stopMotion", "SystemManager")
        msg_dic_snd["Priority"] = priority
        msg_dic_snd["MessageID"] = str(self.messageID)
        self.send_robot_message(msg_dic_snd)
        self.messageID += 1
        return msg_dic_snd["MessageID"]

    def papero_recv(self, t):
        """
        伝文受信
        @param t:タイムアウト(Noneの場合は受信できるまでブロック)
        @return 受信伝文、t秒以内に受信できなかった場合はNone
        """
        try:
            message = self.queFromCom.get(block=True, timeout=t)
            if message is None:
                if not self.scriptMayFinish:
                    self.errOccurred = 2
                    self.errDetail = "Disconnected"
                    logger.error("------Error occurred(papero_recv()). Detail : " + self.errDetail)
        except queue.Empty:
            message = None
        return message

    def papero_robot_message_recv(self, t):
        """
        ロボット伝文受信
        @param t:タイムアウト
        @return 受信伝文の配列、t秒以内に受信できなかった場合はNone
        """
        robot_message = self.papero_recv(t)
        messages = None
        if robot_message is not None:
            msg_dic_rcv = json.loads(robot_message)
            if msg_dic_rcv["Name"] == "RobotMessage":
                messages = msg_dic_rcv["Messages"]
                # Ver.1.01 発話コマンド個数管理
                if messages[0]["Name"] == "startSpeechRes":
                    self.remain_speech_count -= 1
            elif msg_dic_rcv["Name"] == "RobotEnd":
                self.errOccurred = 3
                self.errDetail = "ScriptEnd"
                if not self.scriptMayFinish:
                    self.send_script_abort()
        return messages

    def papero_cleanup(self):
        """
        終了処理
        """
        if self.errOccurred == 0:
            self.send_script_end()
        self.papero_send(None)


def get_numstr_list_from_coord(coord):
    """
    detectFaceイベント等に含まれる座標文字列を整数のリストに分解
    @param coord:"(x,y)"形式の座標文字列
    @return:座標要素(文字列)のリスト
    """
    if (len(coord) > 0) and (coord[0] == "("):
        rtn_list = coord[1:len(coord) - 1].split(",")
    else:
        rtn_list = coord.split(",")
    return rtn_list


def get_params_from_commandline(argv):
    """
    コマンドライン解析
    @return シミュレータID、robot名、WebSocketサーバアドレス
    """
    simulator_id = ""
    robot_name = ""
    ws_server_addr = ""
    state = 0
    for arg in argv[1:]:
        if state == 0:
            if arg == "-sim":
                state = 1
            elif arg == "-robot":
                state = 2
            elif arg == "-wssvr":
                state = 3
        elif state == 1:
            simulator_id = arg
            state = 0
        elif state == 2:
            robot_name = arg
            state = 0
        elif state == 3:
            ws_server_addr = arg
            state = 0
    return simulator_id, robot_name, ws_server_addr
