import sys
import signal
import traceback
from time import sleep
from threading import Lock
from generaltaskthread import Task, TaskThread

class EventHandlerTask(Task):
    # This task is calling the bound function when event was invoked.
    def __init__(self, funcs, *args):
        Task.__init__(self)
        self.funcs = funcs
        self.args = args

    def run(self):
        for func in self.funcs:
            try:
                func(*self.args)
            except:
                traceback.print_exc()

class EventHandlerLoop():
    def __init__(self):
        self.__worker = TaskThread('eventloop')
        self.__worker.start()
        self.__is_down = False
        self.etf_lock = Lock()
        self.evt_to_funcs = {}
        self.timer_interval = 0.01
        self.timer_lock = Lock()
        self.timer_funcs = { "initial_time" : [],
                             "func_to_call" : [],
                             "time_to_call" : [] }

    def shutdown(self):
        self.__worker.stop()
        self.__is_down = True

    def is_shutdown(self):
        return self.__is_down

    def add_binding(self, evt, func):
        # Store the event-to-function_list pair.
        # So all functions which are bound to specific event will be called.
        with self.etf_lock:
            funcs = self.evt_to_funcs.setdefault(evt, [])
            if func not in funcs:
                funcs.append(func)

    def remove_binding(self, evt, func):
        # Remove the event-to-function_list pair.
        with self.etf_lock:
            funcs = self.evt_to_funcs.setdefault(evt, [])
            try:
                funcs.remove(func)
            except:
                print("%s doesn't bound for evt(%s)"%(str(func), evt))

    def dispatch_invoked_evt(self, evt, *args):
        # A task, which will call all functions that are bound to target event, is created.
        funcs = None
        with self.etf_lock:
            funcs = self.evt_to_funcs.get(evt, [])
        if funcs:
            task = EventHandlerTask(funcs, *args)
            self.__worker.addtask(task)

    def set_timer_function(self, sec, func):
        # Provide a way to periodically call func().
        self.timer_lock.acquire()
        if func in self.timer_funcs['func_to_call']:
            print(" There's already a timer for func, return !")
            return
        self.timer_funcs['initial_time'].append(sec)
        self.timer_funcs['func_to_call'].append(func)
        self.timer_funcs['time_to_call'].append(sec)
        self.timer_lock.release()

    def set_timer_interval(self, interval):
        assert interval >= 0.01
        self.timer_interval = interval

    def update_timer(self):
        # This function is called periodically every interval seconds.
        # All bound functions with a default time are re-calculated here to make
        # sure they can be called at correct time.
        with self.timer_lock:
            funcs_to_call = []
            for i in range(len(self.timer_funcs['time_to_call'])):
                self.timer_funcs['time_to_call'][i] -= self.timer_interval
                if self.timer_funcs['time_to_call'][i] <= 0:
                    funcs_to_call.append(self.timer_funcs['func_to_call'][i])
                    self.timer_funcs['time_to_call'][i] = self.timer_funcs['initial_time'][i]
            if funcs_to_call:
                task = EventHandlerTask(funcs_to_call)
                self.__worker.addtask(task)

class EventHandler(object):
    def __init__(self):
        self.evtloop = globals()["__evtloop"]

    def settimer(self, seconds, func):
        assert seconds >= 1, "It's not that healthy doing func in that frequency...are u sure ?"

    def bind(self, evt, func):
        self.evtloop.add_binding(evt, func)

    def unbind(self, evt, func):
        self.evtloop.remove_binding(evt, func)
        pass

    def invoke(self, evt, *args):
        self.evtloop.dispatch_invoked_evt(evt, *args)
        pass

class EventHandlerNotifier(EventHandler):
    def __init__(self):
        EventHandler.__init__(self)
        self.bind('EVT_INVOKED_FROM_NOTIFIER', self.observed_in_notifier)

    def notify_event(self):
        self.invoke('EVT_INVOKED_FROM_NOTIFIER', 'CanYouSeeMe?')
        self.invoke('EVT_INVOKED_FROM_NOTIFIER_TEST_CLASSMETHOD')
        self.invoke('EVT_CALL_OTHERS_METHOD', 'Outside')

    def observed_in_notifier(self, *args):
        print("[Notifier][observed_in_notifier] : %s"%(args))

    @classmethod
    def callback(cls, *args):
        print("[Notifier][callback] classmethod called")

    def called_by_outside_binding(self, *args):
        print("[Notifier][callback] called_by_outside_binding ... ")

class EventHandlerObserver(EventHandler):
    def __init__(self, other):
        EventHandler.__init__(self)
        self.bind('EVT_INVOKED_FROM_NOTIFIER', self.observed)
        self.bind('EVT_INVOKED_FROM_NOTIFIER_TEST_CLASSMETHOD', EventHandlerNotifier.callback)
        self.bind('EVT_CALL_OTHERS_METHOD', other.called_by_outside_binding)

    def observed(self, *args):
        print("[Observer][observed] : %s"%(args))

def _sample_windows():
    evtloop = globals()["__evtloop"]
    evtloop.update_timer()

def _sample_unix(signo, frame):
    evtloop = globals()["__evtloop"]
    evtloop.update_timer()

def config_sigint_handler():
    # Handle Ctrl+C exception.
    global eventloop_started
    evtloop = globals()["__evtloop"]
    def signal_handler(signal, frame):
        print('You pressed Ctrl+C!')
        evtloop.shutdown()
        eventloop_started = False
        assert evtloop.is_shutdown(), "evtloop should be down !"

    # signal.SIGINT will trigger "KeyboardInterrupt" exception
    signal.signal(signal.SIGINT, signal_handler)

def loop_unix(interval):
    global eventloop_started

    # We use "signal" module to get _sample_unix() called periodically in interval sec.
    signal.signal(signal.SIGALRM, _sample_unix)
    signal.setitimer(signal.ITIMER_REAL, interval, interval)

    # We setup another handler to handle single.SIGINT which will be thrown when
    # Ctrl+C is hit.
    config_sigint_handler()

    # NOTE : Calling signal.pause() or not doesn't seem to matter here.
    #        We're only calling evtloop.update_timer() in main thread
    #        when this thread wakes up
    signal.pause()

def loop_windows(interval, evtloop):
    # We setup another handler to handle single.SIGINT which will be thrown when
    # Ctrl+C is hit.
    config_sigint_handler()

    while evtloop and not evtloop.is_shutdown():
        try:
            sleep(interval)
            _sample_windows()
        except:
            print(" down ... ")
    print("bye windows ... ")

eventloop_started = False

def run_eventloop_untill_keyboard_interrupt(func_once):
    # Should only enter once.
    global eventloop_started
    assert not eventloop_started, "Should not run this twice !!"
    eventloop_started = True

    # Make evtloop.update_timer() is called every 0.01s
    interval = 0.01
    evtloop = globals()["__evtloop"]
    evtloop.set_timer_interval(interval)

    # TODO : Enable to run FUNC_FOO() each day
    # evtloop.set_timer_function(86400, FUNC_FOO)
    func_once()

    # NOTE : The goal of following loop_PLATFORM functions is to make sure
    #        functions _sample_unix() / _sample_windows() called every interval sec.
    if sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
        loop_unix(interval)
    elif sys.platform.startswith('win32'):
        loop_windows(interval, evtloop)
    else:
        assert False, "Not supported platform"

def test_eventhandler_notifier_observer():
    # To demo bind / invoke mechanism
    ehn = EventHandlerNotifier()
    eho = EventHandlerObserver(ehn)
    ehn.notify_event()

__evtloop = None
if __name__ == "__main__":
    globals()["__evtloop"] = EventHandlerLoop()
    run_eventloop_untill_keyboard_interrupt(test_eventhandler_notifier_observer)
