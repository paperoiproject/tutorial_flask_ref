import sys

import pypapero

import operation

from flask import Flask, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

papero = pypapero.Papero("iwl2kro4", "", "")

@app.route('/start')
def start():
    operation.hello(papero)
    return "start"

@app.route('/ok')
def ok():
    operation.ok(papero)
    return "ok"

@app.route('/thank')
def thank():
    operation.thank(papero)
    return "thank"

@app.route('/end')
def end():
    operation.bye(papero)
    papero.papero_cleanup()
    return "end"



@app.route("/", methods=["GET", "POST"])
def test():
    if request.method == "GET":
        return """aaa
        """
    else:
        print("post")
        post_data = request.get_json()
        if post_data['work'] == "hello":
            operation.hello(papero)
            return "start"
        if post_data['work'] == "thank":
            operation.thank(papero)
            return "thank"
        if post_data['work'] == "sorry":
            operation.sorry(papero)
            return "sorry"
        if post_data['work'] == "bye":
            operation.bye(papero)
            papero.papero_cleanup()
            return "bye"


        #if request.form['work'] == "hello":
            #return '''a'''
        #else:
            #return '''error'''
















