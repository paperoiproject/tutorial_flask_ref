import sys


def hello(papero):
    if papero.errOccurred == 0:
        papero.send_move_head(["A-15T500L", "A0T500L"],
                              ["A0T500L", "R0T500L"])
        papero.send_turn_led_on("mouth",
                                ["NNNG3G3G3NNN", "2", "NNG3NG3NG3NN", "2", "G3NG3NG3NG3NG3", "2", "G3NG3NG3NG3NG3", "2", "NG3G3G3G3G3G3G3N", "2"])
        papero.send_start_speech("こんにちは")


def ok(papero):
    if papero.errOccurred == 0:
        papero.send_move_head(["A-15T200L", "A15T500L", "A-15T500L", "A15T500L", "A0T300L"],
                              ["A0T200L", "R0T1800L"])
        papero.send_turn_led_on("mouth",
                                ["NNNG3G3G3NNN", "2", "G3NG3NG3NG3NG3", "2", "NNNG3G3G3NNN", "2", "NNNG3G3G3NNN", "2", "NG3G3G3G3G3G3G3N", "2", "G3NG3NG3NG3NG3", "2", "G3NG3NG3NG3NG3", "2", "NG3G3G3G3G3G3G3N", "2", "G3NG3NG3NG3NG3", "2", "NG3G3G3G3G3G3G3N", "2"])
        papero.send_start_speech(" りょうかいしました")

def sorry(papero):
    papero.send_move_head(["A-15T600L", "A-5T400L", "A-10T400L", "A-5T300L", "A-15T800L"],
                          ["A0T600L", "R0T1900L"])
    papero.send_turn_led_on("mouth",
                            ["NNNG3G3G3NNN", "2", "NNG3G3G3G3G3NN", "2", "NNG3NG3NG3NN", "2", "NG3G3G3G3G3G3G3N", "2", "NG3G3G3G3G3G3G3N", "2", "G3NG3NG3NG3NG3", "2"])
    papero.send_start_speech("ごめんなさい")

def thank(papero):
    papero.send_turn_led_on("cheek",
                            ["R3R3", "2", "R3R3", "2", "R3R3", "2", "R3R3", "2", "R3R3", "2", "R3R3", "2", "R3R3", "2", "R3R3", "2", "R3R3", "2", "R3R3", "2"])
    papero.send_turn_led_on("mouth",
                            ["NG3G3G3G3G3G3G3N", "2", "G3NG3NG3NG3NG3", "2", "NG3G3G3G3G3G3G3N", "2", "NNNG3G3G3NNN", "2", "NNNG3G3G3NNN", "2", "NNNG3G3G3NNN", "2", "NG3G3G3G3G3G3G3N", "2", "G3NG3NG3NG3NG3", "2", "NG3G3G3G3G3G3G3N", "2", "NNNG3G3G3NNN", "2"])
    papero.send_start_speech("ありがとうございます")

#実行の終了
def bye(papero):
    if papero.errOccurred == 0:
        papero.send_move_head(["A-15T500L", "A0T500L"],
                              ["A0T500L", "R0T500L"])
        papero.send_turn_led_on("mouth",
                                ["NNNG3G3G3NNN", "2", "NNG3NG3NG3NN", "2", "G3NG3NG3NG3NG3", "2", "G3NG3NG3NG3NG3", "2", "NG3G3G3G3G3G3G3N", "2"])
        papero.send_start_speech("さようなら")
        cnt = 0
        while cnt < 3:
            messages = papero.papero_robot_message_recv(1.0)
            if messages is not None:
                cnt += 1














