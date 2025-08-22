import json, socket, time
HOST, PORT = "127.0.0.1", 34310
with socket.create_connection((HOST, PORT)) as s:
    t=0
    while True:
        t+=1; now=int(time.time())
        arr = [
          {"class":"TQBR","sec":"SBER","last":270+(t%5),"ts":now,"name":"SBER","ddiv":"18.07.2025","divr":34.84,"utv":2},
          {"class":"TQBR","sec":"YDEX","last":5500+(t%7),"ts":now,"name":"YDEX","ddiv":"29.09.2025","divr":80,"utv":1},
          {"class":"SPBFUT","sec":"SRU5","last":(2700*10)+(t%11),"ts":now,"name":"SBER","lot_size":10,"go_contract":12000,"days_to_mat_date":30},
          {"class":"SPBFUT","sec":"YDU5","last":(5500*1)+(t%11),"ts":now,"name":"YDEX","lot_size":1,"go_contract":8000,"days_to_mat_date":30},
        ]
        s.send((json.dumps(arr)+"\n").encode())
        time.sleep(1)
