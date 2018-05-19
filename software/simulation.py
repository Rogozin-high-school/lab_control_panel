"""
BETA Simulation software for experiment system.
Author: Yotam Salmon
"""

# Importing imaging and calculation modules
import numpy as np
import cv2

# Trajectories and field models
from module.models.trajectory.circular2D import CircularTrajectory2D
from module.models.field.tangential2D import TangentialField2D
from module.models.physics.electricity  import field_coil

# Compass module to process the compass image
import module.compass.compass as compass

# Helmholtz module to control the helmholtz coils
import module.hardware.helmholtz as helmholtz

# Magnetometer module to get magnetometer readings.
import module.hardware.magnetometer as magnetometer

# Trivial imports
import time
import os
import threading

class Display(object):
    """
    Display unit for the simulation system.
    """
    def __init__(self, _name, interval=30):
        """
        Creates a new board
        """
        self.screen = np.zeros((600, 800, 3), np.uint8)
        self.display = cv2.namedWindow(_name)
        self.name = _name
        self.renderers = []
        self.interval = interval

    def add_render(self, renderer):
        """
        Adds a renderer to the rendeders list. 
        Every renderer can add or remove elements from the board before it's 
        shown to the user.
        """
        self.renderers.append(renderer)

    def render(self):
        """
        Updates the board and shows it on screen.
        """
        self.screen.fill(255)
        for r in self.renderers:
            self.screen = r(self.screen) or self.screen
        cv2.imshow(self.name, self.screen)
        return cv2.waitKey(self.interval)

    def __del__(self):
        """
        Destroys an active board and closes the window.
        """
        cv2.destroyWindow(self.name)

"""
The satellite position (height, angle) returned from the trajectory model
"""
position = None

"""
The current field (x, y) returned from the field model
"""
fld = None

"""
The compass angle read by the camera module.
"""
cmp_ang = 0

"""
The magnetometer field read by the magnetometer module (Android gaussmeter)
"""
mgm_field = None

"""
The magnetometer field read by the satellite (Raspberry PI + MPU 9250)
"""
sat_mgm_field = None

def render(img):
    """
    Rendering everything on the board.
    """
    global position, fld

    ctr_x = 400
    ctr_y = 300

    """ Center point """
    cv2.circle(img, (ctr_x, ctr_y), 80, (255, 200, 200), -1)
    
    """ Axes """
    cv2.arrowedLine(img, (ctr_x, ctr_y + 50), (ctr_x, ctr_y - 50), (150, 255, 150), 4)
    cv2.arrowedLine(img, (ctr_x - 50, ctr_y), (ctr_x + 50, ctr_y), (255, 150, 150), 4)
    cv2.circle(img, (ctr_x, ctr_y), 6, (150, 150, 255), -1)

    """ Trajectory """
    cv2.circle(img, (ctr_x, ctr_y), 200, (200, 200, 200), 1)

    """ Compass rose """
    cv2.putText(img, "N", (ctr_x - 10, ctr_y - 100), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 0))
    cv2.putText(img, "S", (ctr_x - 10, ctr_y + 120), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 0))
    cv2.putText(img, "E", (ctr_x + 100, ctr_y + 10), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 0))
    cv2.putText(img, "W", (ctr_x - 125, ctr_y + 10), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 0))

    if position is None:
        return

    """ Satellite position """
    sat_x = int(ctr_x + 200 * np.cos(np.radians(position[0])))    
    sat_y = int(ctr_y - 200 * np.sin(np.radians(position[0])))

    """ Expected field vector """
    if fld is not None:
        fld_x = int(fld[0] * 45)
        fld_y = -int(fld[1] * 45)
        cv2.arrowedLine(img, (sat_x, sat_y), (sat_x + fld_x, sat_y + fld_y), (0, 0, 255), 3)
        cv2.arrowedLine(img, (ctr_x, ctr_y), (ctr_x + fld_x, ctr_y + fld_y), (0, 0, 255), 3)

    """ Magnetometer field vector """
    if mgm_field is not None:
        fld_x = int(mgm_field[0] * 0.3)
        fld_y = -int(mgm_field[1] * 0.3)
        cv2.arrowedLine(img, (sat_x, sat_y), (sat_x + fld_x, sat_y + fld_y), (0, 255, 255), 3)
        cv2.arrowedLine(img, (ctr_x, ctr_y), (ctr_x + fld_x, ctr_y + fld_y), (0, 255, 255), 3)

    """ Satellite Magnetometer field vector """
    if sat_mgm_field is not None:
        fld_x = int(sat_mgm_field[0] * 0.3)
        fld_y = -int(sat_mgm_field[1] * 0.3)
        cv2.arrowedLine(img, (sat_x, sat_y), (sat_x + fld_x, sat_y + fld_y), (255, 255, 0), 3)
        cv2.arrowedLine(img, (ctr_x, ctr_y), (ctr_x + fld_x, ctr_y + fld_y), (255, 255, 0), 3)

    """ Compass field vector """
    if cmp_ang:
        cmp_x = int(50 * np.cos(np.radians(cmp_ang)))
        cmp_y = int(-50 * np.sin(np.radians(cmp_ang)))
        cv2.arrowedLine(img, (sat_x, sat_y), (sat_x + cmp_x, sat_y + cmp_y), (0, 255, 0), 3)
        cv2.arrowedLine(img, (ctr_x, ctr_y), (ctr_x + cmp_x, ctr_y + cmp_y), (0, 255, 0), 3)
    
    """ Satellite """
    cv2.circle(img, (sat_x, sat_y), 5, (50, 50, 0), -1)


"""
The field and trajectory processors we want to set up
Field strength was set for the field size to be approx. 0.5 (around 0.57)
Trajectory radius is based on rough real data, and time is accelerated to
match a circle in 1.5 mins.
"""
field = TangentialField2D(6e19)
trajectory = CircularTrajectory2D(7.371e6, 90)

# Starting the compass module
try:
    compass.init()
except:
    pass

# Helmholtz connection
print("==========  Connecting to Helmholtz coils  ==========")
helmholtz.init()
time.sleep(0.5)
print("==========  Resetting Helmholtz coils  ==========")
helmholtz.reset()

"""
Magnetometer reading thread
"""
_work = True
def magnet_read():
    global mgm_field, sat_mgm_field, _work
    while _work:
        mgm_field, sat_mgm_field = magnetometer.get_field()

t = threading.Thread(target=magnet_read)
t.start()

"""
When everything is ready, we initialize the display.
The display unit for visualizing everything
The renderer function is for drawing everything on the board.
"""
display = Display("Indicators window")
display.add_render(render)

t0 = time.time()
while True:

    # Calculating the satellite disposition in space and the expected field we have to 
    # apply according to the models above (circular trajectory and tangential field.)
    dt = time.time() - t0
    position = trajectory.disposition(dt)
    fld = field.field(position)

    f = np.copy(fld)
    f = f * 1e-4
    f = field_coil(1, 150, f)
    helmholtz.set_current(f)

    try:
        #cmp_ang = compass.frame()
        pass
    except:
        cmp_ang = None

    os.system("cls")
    print("Compass:          " + str(cmp_ang) + "deg")
    print("Magnetometer:     " + str(mgm_field))
    print("Satellite mgm:    " + str(sat_mgm_field))
    print("Expected (coils): " + str(f))

    if display.render() & 0xFF == ord('q'):
        break

compass.close()
helmholtz.reset()
helmholtz.close()
_work = False