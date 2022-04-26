# Local modules
import sys
import warnings
from threading import Thread
from time import sleep

# Auxiliary modules
from pymongo import MongoClient
from urllib3.exceptions import InsecureRequestWarning

from epicstel.bot import TelBot
from epicstel.monitor import Monitor

if __name__ == "__main__":
    client = MongoClient("mongodb://localhost:27040/")
    client.admin.authenticate(sys.argv[4], sys.argv[5])

    warnings.simplefilter(action="ignore", category=InsecureRequestWarning)

    debug = sys.argv[-1] == "debug"

    # Needs to be done, cannot replace pyepics printf method
    # if not debug:
    #    sys.stdout = open("data/stdout.log", "w")

    bot = TelBot(sys.argv[1], client, debug)
    mon = Monitor(bot, sys.argv[2], sys.argv[3])

    try:
        bot.logger.info("Initiating monitor thread")
        t = Thread(target=mon.main, daemon=True)
        t_disc = Thread(target=mon.disc, daemon=True)

        t.start()
        t_disc.start()
        while True:
            sleep(10)
            if not t.is_alive() or not t_disc.is_alive():
                bot.thread_is_alive = False
                bot.bot.send_message("403822264", "Thread is dead")
                bot.logger.error("Thread died")
                quit()
    except Exception as e:
        bot.logger.info(e, "Good night")
    except KeyboardInterrupt:
        bot.logger.info("Terminated")
