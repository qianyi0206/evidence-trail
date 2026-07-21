---
source_id: "euroncap_aeb_c2c_v431"
title: "Euro NCAP AEB Car-to-Car Test Protocol"
publisher: "Euro NCAP"
version: "4.3.1"
language: "English"
source_url: "https://cdn.euroncap.com/cars/assets/euro_ncap_aeb_c2c_test_protocol_v431_532926aad1.pdf"
sha256: "71683795b98d60f6478be26c131f3f392d355a599020fd1e77577ac67fce3f1a"
---

# Euro NCAP AEB Car-to-Car Test Protocol (4.3.1)

## Source page 1
<!-- source_id:euroncap_aeb_c2c_v431 page:1 -->

### EUROPEAN NEW CAR ASSESSMENT PROGRAMME
(Euro NCAP)

TEST PROTOCOL – AEB Car-to-Car systems

Implementation 2023

Version 4.3.1
February 2024

## Source page 2
<!-- source_id:euroncap_aeb_c2c_v431 page:2 -->

Copyright 2024 ©Euro NCAP - This work is the intellectual property of Euro NCAP. Permission is granted for this
material to be shared for non-commercial, educational purposes, provided that this copyright statement appears
on the reproduced materials and notice is given that the copying is by permission of Euro NCAP. To disseminate
otherwise or to republish requires written permission from Euro NCAP.

## Source page 3
<!-- source_id:euroncap_aeb_c2c_v431 page:3 -->

EUROPEAN NEW CAR ASSESSMENT PROGRAMME (Euro NCAP)

### TEST PROTOCOL – AEB SYSTEMS

Table of Contents

1 INTRODUCTION ................................................................................................................ 1
2 DEFINITIONS .................................................................................................................... 2

2.1 General ......................................................................................................................................... 2

2.2 Test Scenarios .............................................................................................................................. 3
3 REFERENCE SYSTEM ...................................................................................................... 4

3.1 Convention ................................................................................................................................... 4

3.2 VUT longitudinal path error ...................................................................................................... 6

3.3 VUT Lateral path error .............................................................................................................. 6

3.4 Lateral overlap ............................................................................................................................. 7

3.5 Profiles for impact speed determination.................................................................................... 7
4 MEASURING EQUIPMENT.............................................................................................. 8

4.1 Measurements and Variables ..................................................................................................... 8

4.2 Measuring Equipment ................................................................................................................. 8

4.3 Data Filtering ............................................................................................................................... 9
5 GLOBAL VEHICLE TARGET ........................................................................................... 9

5.1 Specification ................................................................................................................................. 9
6 MANUFACTURER DATA ............................................................................................... 10

6.1 Manufacturer Supplied Data .................................................................................................... 10

6.2 Absence of Manufacturer Data ................................................................................................ 10
7 TEST CONDITIONS ......................................................................................................... 11

7.1 Test Track .................................................................................................................................. 11

7.2 Weather Conditions ................................................................................................................... 12

7.3 Surroundings .............................................................................................................................. 12

7.4 VUT Preparation ....................................................................................................................... 13
8 TEST PROCEDURE ......................................................................................................... 16

8.1 VUT Pre-test Conditioning ....................................................................................................... 16

8.2 Test Scenarios ............................................................................................................................ 17

8.3 Test Conduct .............................................................................................................................. 25

8.4 Test Execution ............................................................................................................................ 25

## Source page 4
<!-- source_id:euroncap_aeb_c2c_v431 page:4 -->

ANNEX A : BRAKE APPLICATION PROCEDURE ............................................................ 27
A.1 Definitions .......................................................................................................................... 27
A.2 Measurements .................................................................................................................... 27
A.3 Brake Characterization Procedure .................................................................................... 27
A.4 Brake Application Profile .................................................................................................. 29
ANNEX B: Lane Change Path Definition ............................................................................... 30
ANNEX C: CCCscp Start from Stop ......................................................................................... 34
C.1 Definitions .......................................................................................................................... 34
C.2 Measurements .................................................................................................................... 34
C.3 Gas-Pedal characterization procedure .............................................................................. 34

## Source page 5
<!-- source_id:euroncap_aeb_c2c_v431 page:5 -->

### 1 INTRODUCTION

Car-to-car rear impacts are one of the most frequent accidents happening on the roads
due to driver distraction or misjudgement. Typical front-to-rear collisions during city
driving are normally occurring at relatively low speeds where the impacted car is
already at standstill, but with a high risk of a debilitating whiplash injury to the driver
of the struck vehicle. While injury severities are usually low, these accidents are very
frequent and represent over a quarter of all crashes. Similar accident scenarios occur on
the open road, at moderate to higher speeds, where a driver might be distracted and may
fail to recognise that the traffic in front of him is stopped, coming to a stop or is driving
at a lower speed.

Other common collision types include those with oncoming or crossing vehicles when
navigating junctions, and oncoming vehicles in case of leaving the lane. Drivers can be
challenged by the more complex nature of the road layout, and the perception,
judgement and dynamic manoeuvring required to successfully navigate safely through
the other traffic.

To support the driver in avoiding these common collision types, car manufactures offer
avoidance technology that warns, supports adequate braking and/or ultimately stops the
vehicle by itself. This protocol specifies the AEB Car-to-Car test procedures aimed at
addressing these common collision types, which are part of the Safety Assist
assessment. To be eligible to score points for AEB Car-to-Car, a good Whiplash score
must be achieved for the front seat. The system is tested in the seven scenarios detailed
in this protocol.

Version 4.3.1
February 2024 1

## Source page 6
<!-- source_id:euroncap_aeb_c2c_v431 page:6 -->

### 2 DEFINITIONS

### 2.1 General

Throughout this protocol the following terms are used:

Peak Braking Coefficient (PBC) – the measure of tyre to road surface friction based
on the maximum deceleration of a rolling tyre, measured using the American Society
for Testing and Materials (ASTM) E1136-10 (2010) standard reference test tyre, in
accordance with ASTM Method E 1337-90 (reapproved 1996), at a speed of 64.4km/h,
without water delivery. Alternatively, the method as specified in UNECE R13-H.

Autonomous Emergency Braking (AEB) – braking that is applied automatically by
the vehicle in response to the detection of a likely collision to reduce the vehicle speed
and potentially avoid the collision.

Forward Collision Warning (FCW) – an audio-visual warning that is provided
automatically by the vehicle in response to the detection of a likely collision to alert the
driver.

Autonomous Emergency Steering (AES) – steering that is applied automatically by
the vehicle in response to the detection of a likely collision to steer the vehicle around
the vehicle in front to avoid the collision.

Emergency Steering Support (ESS) – a system that supports the driver steering input
in response to the detection of a likely collision to alter the vehicle path and potentially
avoid a collision.

Vehicle under test (VUT) – means the vehicle tested according to this protocol with a
pre-crash collision mitigation or avoidance system on board

Vehicle width – the widest point of the vehicle ignoring the rear-view mirrors, side
marker lamps, tyre pressure indicators, direction indicator lamps, position lamps,
flexible mud-guards and the deflected part of the tyre side-walls immediately above the
point of contact with the ground.

Global Vehicle Target (GVT) – means the vehicle target used in this protocol as
defined in ISO 19206-3:2021

Secondary Other Vehicle (SOV) – means the vehicle being overtaken by VUT in
CCFhol scenario. This vehicle can either be a GVT or a real vehicle.

Time To Collision (TTC) – means the remaining time before the VUT strikes the GVT,
assuming that the VUT and GVT would continue to travel with the speed it is travelling.

Version 4.3.1
February 2024 2

## Source page 7
<!-- source_id:euroncap_aeb_c2c_v431 page:7 -->

TAEB – means the time where the AEB system activates. Activation time is determined
by identifying the last data point where the filtered acceleration signal is below -1 m/s2,
and then going back to the point in time where the acceleration first crossed -0.3 m/s2

TFCW – means the time where the audible warning of the FCW starts. The starting point
is determined by audible recognition

Vimpact – means the speed at which the profiled line around the front end of the VUT
coincides with the rectangular shape of the GVT as shown in the right part of Figure
2-1 Front end profile and GVT.

Vrel_impact – means the relative speed at which the VUT hits the GVT by subtracting
the velocity of the GVT from Vimpact at the time of collision.

Figure 2-1 Front end profile and GVT

### 2.2 Test Scenarios

Car-to-Car Rear Stationary (CCRs) – a collision in which a vehicle travels forwards
towards another stationary vehicle and the frontal structure of the vehicle strikes the
rear structure of the other.

Car-to-Car Rear Moving (CCRm) – a collision in which a vehicle travels forwards
towards another vehicle that is travelling at constant speed and the frontal structure of
the vehicle strikes the rear structure of the other.

Car-to-Car Rear Braking (CCRb) – a collision in which a vehicle travels forwards
towards another vehicle that is travelling at constant speed and then decelerates, and the
frontal structure of the vehicle strikes the rear structure of the other.

Car-to-Car Front Turn-Across-Path (CCFtap) – a collision in which a vehicle turns

Version 4.3.1
February 2024 3

## Source page 8
<!-- source_id:euroncap_aeb_c2c_v431 page:8 -->

across the path of an oncoming vehicle travelling at constant speed, and the frontal
structure of the vehicle strikes the front structure of the other.

Car-to-Car Crossing Straight Crossing Path (CCCscp) – a collision in which a
vehicle travels forwards along a straight path across a junction, towards a vehicle
crossing the junction on a perpendicular path. The frontal structure of the vehicle
under test strikes the side of the other vehicle.

Car-to-Car Front Head-On Straight (CCFhos) – a collision where a vehicle is
travelling along a straight path within its defined lane and strikes another vehicle
travelling in the opposite direction, which has drifted into the same lane as the original
vehicle. The frontal structure of the vehicle strikes the frontal structure of the other.

Car-to-Car Front Head-On Lane change (CCFhol) – a collision where a vehicle is
travelling along a straight path within its defined lane and strikes another vehicle
travelling in the opposite direction which has intentionally moved into the lane of the
original vehicle to attempt an overtake. The frontal structure of the vehicle strikes the
frontal structure of the other.

### 3 REFERENCE SYSTEM

### 3.1 Convention
3.1.1 For both VUT and GVT use the convention specified in ISO 8855:1991 in which the x-
axis points towards the front of the vehicle, the y-axis towards the left and the z-axis
upwards (right hand system), with the origin at the most forward point on the centreline
of the VUT for dynamic data measurements as shown in Figure 3-1.
### 3.1.2 Viewed from the origin, roll, pitch and yaw rotate clockwise around the x, y and z axes
respectively. Longitudinal refers to the component of the measurement along the x-axis,
lateral the component along the y-axis and vertical the component along the z-axis.
3.1.3 This reference system should be used for both left- and right-hand drive vehicles tested.
3.1.4 The nearside is swapped as per LHD and RHD vehicles. Figure 3-1 shows the near and
farside of the vehicle for a left hand driven (LHD) vehicle.

Version 4.3.1
February 2024 4

## Source page 9
<!-- source_id:euroncap_aeb_c2c_v431 page:9 -->

Figure 3-1: Coordinate system and notation

Version 4.3.1
February 2024 5

## Source page 10
<!-- source_id:euroncap_aeb_c2c_v431 page:10 -->

### 3.2 VUT longitudinal path error
### 3.2.1 The VUT longitudinal path error is determined as the difference between the desired
position and the actual position of the front of the VUT when measured at a single
defined “stable” position of the front of the GVT during the test.

VUT longitudinal path error = XVUT, desired – XVUT, actual (@XGVT)

For CCFtap, when the origin of the reference system is at the intended collision point,
the values shown in the table below shall be used to determine the VUT longitudinal
path error.

VUT speed GVT speed XVUT, desired XGVT
30 km/h 29.17 m
10 km/h 45 km/h - 9.57 m 43.75 m
60 km/h 58.33 m
30 km/h 29.17 m
15 km/h 45 km/h - 14.53 m 43.75 m
60 km/h 58.33 m
30 km/h 29.17 m
20 km/h 45 km/h - 19.47 m 43.75 m
60 km/h 58.33 m

### 3.3 VUT Lateral path error
### 3.3.1 The lateral path error is determined as the lateral distance between the centre of the
front axle of the VUT and the centre of the rear of the GVT when measured in parallel
to the intended straight-lined path as shown in the figure below.

Lateral path error = YVUT error + YGVT error

Figure 3-2: Lateral path error

Version 4.3.1
February 2024 6

## Source page 11
<!-- source_id:euroncap_aeb_c2c_v431 page:11 -->

### 3.4 Lateral overlap
### 3.4.1 The lateral overlap is defined as a percentage of the width of the VUT overlapping the
GVT, where the reference line for the overlap definition is the centreline of the VUT.
In case of 100% overlap, the centrelines of the VUT and GVT are aligned.

Figure 3-3: Lateral Overlap examples

### 3.5 Profiles for impact speed determination
3.5.1 A virtual profiled line is defined around the front end of the VUT. This line is defined
by straight line segments connecting seven points that are equally distributed over the
vehicle width minus 50mm on each side. The theoretical x,y coordinates are provided
by the OEMs and verified by the test laboratory.

Figure 3-4 VUT Front bumper profile

Version 4.3.1
February 2024 7

## Source page 12
<!-- source_id:euroncap_aeb_c2c_v431 page:12 -->

### 4 MEASURING EQUIPMENT

4.1.1 Sample and record all dynamic data at a frequency of at least 100Hz. Synchronise using
the DGPS time stamp the GVT data with that of the VUT.

### 4.1 Measurements and Variables

### 4.1.1 Time T
• T0, time of test start. Unless otherwise stated T0 = TTC 4s T0
▪ Scenarios involving steering: T0 is 1s. before Tsteer
• TAEB, time where AEB activates TAEB
• TFCW, time where FCW activates TFCW
• Timpact, time where VUT impacts GVT Timpact
• Tsteer, time where VUT enters in curve segment Tsteer
• TGVT_deceleration_start , time where GVT starts decelerating TGVT_deceleration_start
(deceleration to be reached in 1.0 seconds)
• TStart, time where VUT starts moving TStart
(iFn CCCscp start from stop scenario)

• TEnd, time where VUT has travelled 2.9m. from the start position TEnd
(in CCCscp start from stop scenario)
• TAvg, average time value of TEnd from all the executed trials TAvg
(in CCCscp start from stop scenario)

### 4.1.2 Position of the VUT during the entire test XVUT, YVUT
### 4.1.3 Position of the GVT during the entire test XGVT, YGVT
### 4.1.4 Speed of the VUT during the entire test VVUT
• Vimpact, speed when VUT impacts GVT Vimpact
• Vrel_impact, relative speed when VUT impacts GVT Vrel_impact
VGVT 4.1.5 Speed of the GVT during the entire test
4.1.6 Yaw velocity of the VUT during the entire test 𝜳̇ VUT
4.1.7 Yaw velocity of the GVT during the entire test 𝜳̇ GVT
### 4.1.8 Acceleration of the VUT during the entire test AVUT
### 4.1.9 Acceleration of the GVT during the entire test AGVT
4.1.10 Steering wheel velocity of the VUT during the entire test ΩVUT

### 4.2 Measuring Equipment
### 4.2.1 Equip the VUT and GVT with data measurement and acquisition equipment to sample
and record data with an accuracy of at least:

Version 4.3.1
February 2024 8

## Source page 13
<!-- source_id:euroncap_aeb_c2c_v431 page:13 -->

• VUT and GVT speed to 0.1km/h;
• VUT and GVT lateral and longitudinal position to 0.03m;
• VUT heading angle to 0.1°;
• VUT and GVT yaw rate to 0.1°/s;
• VUT and GVT longitudinal acceleration to 0.1m/s2;
• VUT steering wheel velocity to 1.0 °/s.

### 4.3 Data Filtering
4.3.1 Filter the measured data as follows:
4.3.1.1 Position and speed are not filtered and are used in their raw state.
### 4.3.1.2 Acceleration, yaw rate, steering wheel velocity and force are filtered with a 12-pole
phase less Butterworth filter with a cut off frequency of 10Hz.

### 5 GLOBAL VEHICLE TARGET

### 5.1 Specification
### 5.1.1 Conduct the tests in this protocol using the Global Vehicle Target (GVT) as shown in
Figure 5-1 below. The GVT replicates the visual, radar and LIDAR attributes of a
typical M1 passenger vehicle.

Figure 5-1: Global Vehicle Target (GVT)

### 5.1.2 To ensure repeatable results the combination of the propulsion system and GVT must
meet the requirements as detailed in ISO 19206-3:2021.
5.1.3 Only equipment listed in the current version of TB029 – Suppliers List may be used for
testing. The current version can be found on the Euro NCAP website.
5.1.4 The GVT is designed to work with the following types of sensors:
• Radar (24 and 77 GHz)
### • LIDAR
• Camera
When a manufacturer believes that the GVT is not suitable for another type of sensor
system used by the VUT but not listed above, the manufacturer is asked to contact the
Euro NCAP Secretariat.

Version 4.3.1
February 2024 9

## Source page 14
<!-- source_id:euroncap_aeb_c2c_v431 page:14 -->

### 6 MANUFACTURER DATA

### 6.1 Manufacturer Supplied Data
### 6.1.1 The vehicle manufacturer is required to provide the Euro NCAP Secretariat with colour
data (expected impact speeds are not required) detailing the performance of the vehicle
in the CCRs and CCRm scenarios for all overlap and impact speed combinations. The
prediction is to be done for both AEB and FCW system tests where applicable.
### 6.1.2 All data must be supplied by the manufacturer before any testing begins, preferably
with delivery of the test vehicle(s).
### 6.1.3 Data shall be provided for each grid point for CCRs (10-50km/h for AEB and 55-
80km/h for FCW) and CCRm (30-80km/h for AEB) according to the colour scheme
detail in the Euro NCAP Assessment Protocol – Safety Assist Section 4.3.2.
### 6.1.4 The vehicle manufacturer is required to provide the Euro NCAP Secretariat with data
detailing the performance of the vehicle in the CCCscp scenario for all test speed
combinations. The prediction is to be provided for both AEB and FCW system tests
where applicable. Where predictions state insufficient performance to score points, the
tests will not be performed.
### 6.1.5 For the Car-to-Car head-on scenarios the vehicle manufacturer must supply a dossier
detailing how their vehicle responds in the CCFhol and CCFhos test scenarios. The
dossier must, at least, include:
• System performance: The expected performance of the system (TTC of warning –
when applicable – , TTC of AEB activation and speed reduction)
• System architecture: Sensor(s) setup used in perception and basic description of
sensor fusion and decision-making logic
• System operational conditions/limitations (ODD): system activation speed range,
maximum relative speed, overlap range, lighting/environmental conditions,
considered vehicle types (passenger car only or motorcycle, truck, etc), required
lane width(s), required lane marking, etc.
• System overriding conditions: e.g., accelerator pedal %, brake pedal, steering
wheel angle/rate, etc.
• System validation: Evidence of system verification conducted by OEM (physical
tests, HiL/SiL/ViL…)
• Real world performance: Evidence from the vehicle manufacturer demonstrating
the effectiveness of the head-on function on the field (including false positive
likelihood & mitigation strategies)

### 6.2 Absence of Manufacturer Data
### 6.2.1 Where predicted data is NOT provided by the vehicle manufacturer, ALL grid points
are to be tested by the Euro NCAP laboratory, taking into account symmetry (except
for CCCscp Start From Stop setup, where only farside is tested).
### 6.2.1.1 For CCR AEB and FCW systems tests, when there is complete avoidance, the
subsequent test speed for the next test is incremented with 10km/h. When there is

Version 4.3.1
February 2024 10

## Source page 15
<!-- source_id:euroncap_aeb_c2c_v431 page:15 -->

contact, first perform a test at a test speed 5km/h less than the test speed where contact
occurred. After this test continue to perform the remainder of the tests with speed
increments of 5km/h by repeating section 8.3.1 to8.3.3. Stop testing when the speed
reduction seen in the test is less than 5 km/h or the (relative) impact speed is more than
50 km/h.
### 6.2.1.2 For CCCscp tests should be performed starting with the lowest VUT and GVT speed
combination. The next test will use the same VUT test speed and the GVT speed will
be incremented by 10km/h. Where the GVT test speed reaches 60km/h, the next test
will be the combination of the VUT speed increased to the next increment, and a GVT
speed of 10km/h. Continue this method for all VUT test speeds.

### 7 TEST CONDITIONS

### 7.1 Test Track
### 7.1.1 Conduct tests on a dry (no visible moisture on the surface), uniform, solid-paved surface
with a consistent slope between level and 1%. The test surface shall have a minimal
peak braking coefficient (PBC) of 0.9.
7.1.2 The surface must be paved and may not contain irregularities (e.g. large dips or cracks,
manhole covers or reflective studs) that may give rise to abnormal sensor measurements
within a lateral distance of 5.0m to either side of the test path and with a longitudinal
distance of 20m ahead of the VUT when the test ends.
7.1.3 The presence of lane markings is allowed for CCR tests. However, testing may only be
conducted in an area where typical road markings depicting a driving lane may not be
parallel to the test path within 3.0m either side. Lines or markings may cross the test
path but may not be present in the area where AEB activation and/or braking after FCW
is expected.
### 7.1.4 Junction and Lane Markings
7.1.4.1 The CCFtap and CCCscp tests described in this document requires the use of a junction.
The main approach lane where the VUT and GVT paths start, (horizontal lanes in Figure
7-1) will have a width of 3.5m. The side lane (vertical lanes in Figure 7-1) will have a
width of 3.25 to 3.5m. The lane markings on these lanes need to conform to one of the
lane markings as defined in UNECE Regulation 130:
### 1. Dashed line starting at the same point where the radius transitions into a straight
line with a width between 0.10 and 0.15m
2. Solid line with a width between 0.10 and 0.25m
### 3. Junction without any central markings

Version 4.3.1
February 2024 11

## Source page 16
<!-- source_id:euroncap_aeb_c2c_v431 page:16 -->

Figure 7-1: Layout of junction and the connecting lanes

### 7.2 Weather Conditions
7.2.1 Conduct tests in dry conditions with ambient temperature above 5°C and below 40°C.
### 7.2.2 No precipitation shall be falling and horizontal visibility at ground level shall be greater
than 1km. Wind speeds shall be below 10m/s to minimise GVT and VUT disturbance.
### 7.2.3 Natural ambient illumination must be homogenous in the test area and in excess of 2000
lux for daylight testing with no strong shadows cast across the test area other than those
caused by the VUT or GVT. Ensure testing is not performed driving towards, or away
from the sun when there is direct sunlight.
### 7.2.4 Measure and record the following parameters preferably at the commencement of every
single test or at least every 30 minutes:
a) Ambient temperature in °C;
b) Track Temperature in °C;
c) Wind speed and direction in m/s;
d) Ambient illumination in Lux.

### 7.3 Surroundings
### 7.3.1 Conduct testing such that there are no other vehicles, highway infrastructure (except
lighting columns during the low ambient lighting condition tests), obstructions, other
objects or persons protruding above the test surface, that may give rise to abnormal
sensor measurements during the full duration of the test starting at T0 and within a
longitudinal distance 20m ahead of the VUT when the test ends, within:
- 5m either side of the VUT test path,
- a circle around the GVT, and
- the visual axis between the geometric centre of the VUT and the circle
surrounding the GVT.
- For CCCscp only, the above applies from TTC =3.5s (instead of T0).

Version 4.3.1
February 2024 12

## Source page 17
<!-- source_id:euroncap_aeb_c2c_v431 page:17 -->

Position @ TTC 3.5s

Position @ TTC 3.5s

Figure 7-3: Free space requirements – CCC Farside Test

### 7.3.2 Test areas where the VUT needs to pass under overhead signs, bridges, gantries or other
significant structures are not permitted.
### 7.3.3 The general view ahead and to either side of the test area shall comprise of a wholly
plain man made or natural environment (e.g. further test surface, plain coloured fencing
or hoardings, natural vegetation or sky etc.) and must not comprise any highly reflective
surfaces or contain any vehicle-like silhouettes that may give rise to abnormal sensor
measurements.

### 7.4 VUT Preparation

### 7.4.1 AEB and FCW System Settings
7.4.1.1 Set any driver configurable elements of the AEB and/or FCW system (e.g. the timing
of the collision warning or the braking application if present) to the middle setting or
midpoint and then next latest setting similar to the examples shown in Figure 7-2.
When the vehicle is equipped with a Driver State Monitoring (DSM) which alters the
AEB and/or FCW sensitivity according to the driver’s state (e.g. distracted / attentive),
this system shall be deactivated before the testing commences.

Figure 7-2: AEB and/or FCW system setting for testing

Version 4.3.1
February 2024 13

## Source page 18
<!-- source_id:euroncap_aeb_c2c_v431 page:18 -->

### 7.4.2 Deployable Pedestrian/VRU Protection Systems
When the vehicle is equipped with a deployable pedestrian/VRU protection system,
this system shall be deactivated before the testing commences.

### 7.4.3 Tyres
Perform the testing with new original fitment tyres of the make, model, size, speed and
load rating as specified by the vehicle manufacturer. It is permitted to change the tyres
which are supplied by the manufacturer or acquired at an official dealer representing
the manufacturer if those tyres are identical make, model, size, speed and load rating to
the original fitment. Inflate the tyres to the vehicle manufacturer’s recommended cold
tyre inflation pressure(s). Use inflation pressures corresponding to least loading normal
condition.
Run-in tyres according to the tyre conditioning procedure specified in 8.1.3. After
running-in maintain the run-in tyres in the same position on the vehicle for the duration
of the testing.

### 7.4.4 Wheel Alignment Measurement and Unladen Kerb Mass
The vehicle should be subject to a vehicle (in-line) geometry check to record the wheel
alignment set by the OEM. This should be done with the vehicle in kerb weight.
7.4.4.1 Fill up the tank with fuel to at least 90% of the tank’s capacity of fuel.
7.4.4.2 Check the oil level and top up to its maximum level if necessary. Similarly, top up the
levels of all other fluids to their maximum levels if necessary.
### 7.4.4.3 Ensure that the vehicle has its spare wheel on board, if fitted, along with any tools
supplied with the vehicle. Nothing else should be in the car.
7.4.4.4 Ensure that all tyres are inflated according to the manufacturer’s instructions for the
appropriate loading condition.
7.4.4.5 Measure the front and rear axle masses and determine the total mass of the vehicle. The
total mass is the ‘unladen kerb mass’ of the vehicle. Record this mass in the test details.
### 7.4.4.6 Calculate the required ballast mass, by subtracting the mass of the test driver and test
equipment from the required 200 kg interior load.

### 7.4.5 Vehicle Preparation
7.4.5.1 Fit the on-board test equipment and instrumentation in the vehicle. Also fit any
associated cables, cabling boxes and power sources.
7.4.5.2 Place weights with a mass of the ballast mass. Any items added should be securely
attached to the car.
7.4.5.3 With the driver in the vehicle, weigh the front and rear axle loads of the vehicle.
7.4.5.4 Compare these loads with the “unladen kerb mass”

Version 4.3.1
February 2024 14

## Source page 19
<!-- source_id:euroncap_aeb_c2c_v431 page:19 -->

7.4.5.5 The total vehicle mass shall be within ±1% of the sum of the unladen kerb mass, plus
200kg. The front/rear axle load distribution needs to be within 5% of the front/rear axle
load distribution of the original unladen kerb mass plus full fuel load. If the vehicle
differs from the requirements given in this paragraph, items may be removed or added
to the vehicle which has no influence on its performance. Any items added to increase
the vehicle mass should be securely attached to the car.
7.4.5.6 Repeat paragraphs 7.4.5.3 and 7.4.5.4 until the front and rear axle loads and the total
vehicle mass are within the limits set in paragraph 7.4.5.5. Care needs to be taken when
adding or removing weight in order to approximate the original vehicle inertial
properties as close as possible. Record the final axle loads in the test details. Record the
axle weights of the VUT in the ‘as tested’ condition.

Version 4.3.1
February 2024 15

## Source page 20
<!-- source_id:euroncap_aeb_c2c_v431 page:20 -->

### 8 TEST PROCEDURE

### 8.1 VUT Pre-test Conditioning
### 8.1.1 General
8.1.1.1 A new car is used as delivered to the test laboratory.
### 8.1.1.2 If requested by the vehicle manufacturer, drive a maximum of 100km on a mixture of
urban and rural roads with other traffic and roadside furniture to ‘calibrate’ the sensor
system. Avoid harsh acceleration and braking.

### 8.1.2 Brakes
8.1.2.1 Condition the vehicle’s brakes in the following manner, if it has not been done before
or in case the lab has not performed a 100km of driving:
• Perform twenty stops from a speed of 56km/h with an average deceleration of
approximately 0.5 to 0.6g.
• Immediately following the series of 56km/h stops, perform three additional stops
from a speed of 72km/h, each time applying sufficient force to the pedal to operate
the vehicle’s antilock braking system (ABS) for the majority of each stop.
• Immediately following the series of 72km/h stops, drive the vehicle at a speed of
approximately 72km/h for five minutes to cool the brakes.

### 8.1.3 Tyres
8.1.3.1 Condition the vehicle’s tyres in the following manner to remove the mould sheen, if
this has not been done before for another test or in case the lab has not performed a
100km of driving:
• Drive around a circle of 30m in diameter at a speed sufficient to generate a
lateral acceleration of approximately 0.5 to 0.6g for three clockwise laps
followed by three anticlockwise laps.
• Immediately following the circular driving, drive four passes at 56km/h,
performing ten cycles of a sinusoidal steering input in each pass at a frequency
of 1Hz and amplitude sufficient to generate a peak lateral acceleration of
approximately 0.5 to 0.6g.
• Make the steering wheel amplitude of the final cycle of the final pass double
that of the previous inputs.
### 8.1.3.2 In case of instability in the sinusoidal driving, reduce the amplitude of the steering input
to an appropriately safe level and continue the four passes.

Version 4.3.1
February 2024 16

## Source page 21
<!-- source_id:euroncap_aeb_c2c_v431 page:21 -->

### 8.1.4 AEB/FCW System Check

### 8.1.4.1 Before any testing begins, perform a maximum of ten runs at the lowest test speed the
system is supposed to work, to ensure proper functioning of the system.

### 8.2 Test Scenarios
### 8.2.1 The performance of the AEB/FCW system is assessed in the CCRs, CCRm, CCRb,
CCFtap, CCCscp and CCFhos/CCFhol scenarios as shown in the sections 8.2.3 to 8.2.5.
### 8.2.1.1 For CCRs AEB, CCRs FCW and CCRm, the assessment is based on a GRID prediction
provided by the OEM. The actual scenarios to be tested to verify the prediction will be
chosen randomly, distributed in line with the predicted colour distribution (excluding
red points).
The vehicle sponsor will fund 15 verification tests, where applicable. For AEB 10 tests
(CCRs and CCRm) and 5 tests for FCW (CCRs).
The vehicle manufacturer has the option of sponsoring up to 10 additional verification
tests for AEB CCR and 10 for FCW.
8.2.1.2 For CCRb and CCFtap verification tests are conducted at all test points.
### 8.2.1.3 For CCCscp verification tests are conducted at all test points where sufficient
performance to score points is predicted.
### 8.2.2 For CCR testing purposes, assume a straight-line path equivalent to the centreline of
the lane in which the collision occurred, hereby known as the test path. Control the VUT
with driver inputs or using alternative control systems that can modulate the vehicle
controls as necessary to perform the tests.
### 8.2.2.1 Car-to-Car Rear stationary
The CCRs scenario is a combination of speed and overlap with 5km/h incremental steps
in speed and 25% steps in overlap within the ranges as shown in the tables below.

Figure 8-1: CCRs scenario
AEB + FCW combined
AEB only FCW only
### AEB FCW
10-50 km/h 55-80 km/h 10-80 km/h 55-80 km/h
AEB CCRs -50% to 50% -50% to 50% -50% to 50% -50% to 50%

ESS tests will only be allowed for the -50% overlap situation for left hand drive
vehicles (50% for right hand drive).

Version 4.3.1
February 2024 17

## Source page 22
<!-- source_id:euroncap_aeb_c2c_v431 page:22 -->

### 8.2.2.2 Car-to-Car Rear moving
The CCRm scenario is a combination of speed and overlap with 5km/h incremental
steps in speed and 25% steps in overlap within the ranges as shown in the tables below.

Figure 8-2: CCRm scenario

AEB + FCW combined & AEB Only
AEB
30-80 km/h
AEB CCRm -50%-50%

### 8.2.2.3 Car-to-Car Rear braking
The CCRb tests will be performed at a fixed speed of 50km/h for both VUT and GVT
with all combinations of -2 and -6m/s² acceleration and 12 and 40m headway. Different
overlap situations may be tested for monitoring purpose at the end of the test program.

Figure 8-3: CCRb scenario

AEB+FCW combined & AEB only
-2 m/s2 -6 m/s2
12m 50 km/h 50 km/h
AEB CCRb
40m 50 km/h 50 km/h

For CCRb T0 = TGVT_deceleration_start – 1s.
T0 begins 1 second before GVT starts deceleration, for tolerance monitoring purposes.
The desired deceleration of the GVT shall be reached within 1.0 second (T0 + 2.0s)
which after the GVT shall remain within ± 0.5 km/h of the reference speed profile,
derived from the desired deceleration, until the vehicle speed equals 2km/h.

Version 4.3.1
February 2024 18

## Source page 23
<!-- source_id:euroncap_aeb_c2c_v431 page:23 -->

### 8.2.3 Car-to-Car Front turn-across-path
### 8.2.3.1 For the CCFtap scenario, for the VUT assume an initial straight-line path followed by
a turn (clothoid, fixed radius and clothoid as specified in section 8.2.3.5), followed again
by a straight line, hereby known as the test path.
8.2.3.2 The GVT will follow a straight-line path in the lane adjacent to the VUT’s initial
position, in the opposite direction to the VUT. The straight-line path of the VUT and
GVT will be 1.75m from the centre of the centre dashed lane marking of the VUT lane.

Figure 8-4: CCFtap scenario VUT and GVT paths

### 8.2.3.3 The paths of the VUT and target vehicle will be synchronised so that the front edges of
the vehicle meet with a lateral position that gives a 50% overlap (assuming no system
reaction) of the width of the VUT. The VUT longitudinal path error shall be within ±
[0.5] m when determined in accordance with section 3.2.1.

Figure 8-5: CCFtap scenario paths and impact definition

Version 4.3.1
February 2024 19

## Source page 24
<!-- source_id:euroncap_aeb_c2c_v431 page:24 -->

### 8.2.3.4 The CCFtap scenarios are all combinations of VUT speeds of 10, 15 and 20 km/h
combined with GVT speeds of 30, 45 and 60 km/h.
### 8.2.3.5 The following parameters should be used to create the test paths where the turn signal
is applied at 1.0s ±0.5s before Tsteer:

Figure 8-6: CCFtap scenario paths definition

### 8.2.4 Car-to-car Crossing Straight Crossing Path (CCCscp)
### 8.2.4.1 For the VUT assume a straight-line path equivalent to the centre line of the driving lane,
approaching and continuing straight ahead across a junction.
### 8.2.4.2 For the GVT assume a straight-line path equivalent to the centre line of the driving lane,
perpendicular to that of the VUT, travelling across the junction. The scenario is
represented in Figure 8-7 Straight Crossing Path VUT and GVT paths and Figure 8-9
SCP start from stop setup, where ‘//-//’ indicates a vehicle being centred in the driving
lane. For the start from stop tests the GVT travels across the junction from the farside
direction. For all other test speed combinations the GVT will travel from either the
nearside or farside direction, selected at random by the test laboratory.
8.2.4.3 To achieve the correct GVT speed, the GVT must be accelerated at a rate >1m/s2 during
the acceleration phase. This is followed by a 0.5s stabilization phase, after which steady
state conditions must be met as per 8.4.2.
### 8.2.4.4 The paths will be synchronised to that the centre front of the VUT collides with the side
of the GVT, 25% along the length of the GVT (assuming no system reaction).

Version 4.3.1
February 2024 20

## Source page 25
<!-- source_id:euroncap_aeb_c2c_v431 page:25 -->

Figure 8-7 Straight Crossing Path VUT and GVT paths

Figure 8-8 SCP Impact point definition

### 8.2.4.5 For the Start from stop scenario the VUT is at standstill with an initial longitudinal
distance to the GVTs side of 2.9 m (Figure 8-9). Apply brake pedal to ensure that VUT
is stationary until T0 condition is reached, and then conduct the Gas-Pedal profile as
described in ANNEX C: CCCscp Start from Stop. Determination of T0 to ensure
correct impact location (as in 8.2.4.4.) is also described in ANNEX C: CCCscp Start
from Stop. The junction has no further markings (e.g. Stop line).

Version 4.3.1
February 2024 21

## Source page 26
<!-- source_id:euroncap_aeb_c2c_v431 page:26 -->

Figure 8-9 SCP start from stop setup

### 8.2.4.6 In the CCCscp scenario, AEB performance is tested at every combination of VUT and
GVT speed shown in the table below (where sufficient performance to score points is
predicted). FCW performance is tested at all tests with a VUT speed ≥ 40km/h (where
sufficient performance to score points is predicted).

### VUT GVT
20 km/h 30 km/h 40 km/h 50 km/h 60 km/h
Start from stop AEB AEB AEB AEB AEB
20 km/h AEB AEB AEB AEB AEB
30 km/h AEB AEB AEB AEB AEB
40 km/h AEB/FCW AEB/FCW AEB/FCW AEB/FCW AEB/FCW
50 km/h AEB/FCW AEB/FCW AEB/FCW AEB/FCW AEB/FCW
60 km/h AEB/FCW AEB/FCW AEB/FCW AEB/FCW AEB/FCW

### 8.2.4.7 Where a test scenario is avoided by AEB, do not test the same combination for FCW
performance as points are awarded automatically.

Version 4.3.1
February 2024 22

## Source page 27
<!-- source_id:euroncap_aeb_c2c_v431 page:27 -->

### 8.2.5 Car-to-Car Front Head-On (CCFho)
8.2.5.1 VUT and SOV speeds shall be equal for all CCFho scenarios.
### 8.2.5.2 The CCFhos and CCFhol tests described in this document require use of two different
types of lane markings conforming to one of the lane markings as defined in UNECE
Regulation 130 to mark a lane with a width of 3.5 to 3.7m when measured from the
inside edge of the lane marking:

- Dashed line with a width between 0.10 and 0.25m (0.10 and 0.15m for centerlines)
- Solid line with a width between 0.10 and 0.25m

### 8.2.5.3 For the CCFhos/CCFhol scenarios of the OEM must demonstrate, by means of a
dossier, how their system responds in the following scenario. Points will be awarded
based on the information provided in the dossier. Euro NCAP reserve the right to
undertake physical testing in the CCFhos/CCFhol scenarios to verify the information in
the dossier, using the method detailed below.
### 8.2.5.4 Both the CCFhos and CCFhol scenario will be assessed at test speed combinations of
50km/h for VUT and 50km/h for GVT and 70km/h for VUT and 70km/h for GVT
respectively.
### 8.2.5.5 For the CCFhos/CCFhol scenarios, for the VUT assume a straight-line path in the
middle of the lane at a constant speed.
### 8.2.5.6 For the CCFhos scenario, the GVT will follow the same path as the VUT, travelling in
the opposite direction at a constant speed equal to that of the VUT.
### 8.2.5.7 For the CCFhol scenario, the GVT will follow an initial straight-line path followed by
a lane change manoeuvre at a constant speed equal to that of the VUT. The scenarios
are represented in Figure 8-10 CCFhos and Figure 8-12 CCFhol path at 70 and 50 km/h
Details on VUT path is given on ANNEX B: Lane Change Path Definition.

Figure 8-10 CCFhos

Version 4.3.1
February 2024 23

## Source page 28
<!-- source_id:euroncap_aeb_c2c_v431 page:28 -->

Figure 8-11 CCFhol

Figure 8-12 CCFhol path at 70 and 50 km/h

Figure 8-13 CCFhol curvature values at 70 and 50 km/h

GVT VUT Lane Lane Following TTC at Max Lateral
Speed Speed change change Distance end of lane acceleration
offset (O) length (L) (F) change
50km/h 50km/h 3.5m 44m [13.9]m [1.5] s 1.50 m/s²
70km/h 70km/h 3.5m 60m [19.4]m [1.5] s 1.50 m/s²

Version 4.3.1
February 2024 24

## Source page 29
<!-- source_id:euroncap_aeb_c2c_v431 page:29 -->

### 8.3 Test Conduct
### 8.3.1 Before every test run, drive the VUT around a circle of maximum diameter 30m at a
speed less than 10km/h for one clockwise lap followed by one anticlockwise lap, and
then manoeuvre the VUT into position on the test path. If requested by the OEM a
simple initialisation run may be included before every test run. Bring the VUT to a halt
and push the brake pedal through the full extent of travel and release.
8.3.2 For vehicles with an automatic transmission select D. For vehicles with a manual
transmission select the highest gear where the RPM will be at least 1500 at the test
speed. If fitted, a speed limiting device or cruise control may be used to maintain the
VUT speed (not ACC), unless the vehicle manufacturer shows that there are
interferences of these devices with the AEB system in the VUT. Apply only minor
steering inputs as necessary to maintain the VUT tracking along the test path.
### 8.3.3 Perform the first test a minimum of 90s and a maximum of 10 minutes after completing
the tyre conditioning (if applicable), and subsequent tests after the same time period. If
the time between consecutive tests exceeds 10 minutes perform three brake stops from
72 km/h at approximately 0.3g.
Between tests, manoeuvre the VUT at a maximum speed of 50km/h and avoid riding
the brake pedal and harsh acceleration, braking or turning unless strictly necessary to
maintain a safe testing environment.

### 8.4 Test Execution
8.4.1 Accelerate the VUT and GVT (if applicable) to the respective test speeds.
### 8.4.2 The test shall start at T0 and is valid when all boundary conditions are met between T0
and TAEB and/or TFCW, or any other system intervention:

Remark VUT GVT

Constant state + 1.0 ± 1.0
Speed [km/h]
Deceleration state ± 0.5

CCR, CCCscp, CCFhos, CCFhol 0 ± 0.05

Lateral deviation [m] CCFtap(initial straight-line path) 0 ± 0.05 0 ± 0.10

CCFtap(turn) 0 ± 0.10

Relative distance VUT and GVT [m] CCRb only 12 or 40 ± 0.5

Yaw velocity CCFtap (until Tsteer) [°/s] 0 ± 1.0

Steering wheel velocity CCFtap (until Tsteer) [°/s] 0 ± 15.0

8.4.3 The end of a test is considered when one of the following occurs:
- VVUT = 0km/h*
- VVUT < VGVT for CCR
- Contact between VUT and GVT
- The GVT has left the path of the VUT (CCFtap and CCCscp)

Version 4.3.1
February 2024 25

## Source page 30
<!-- source_id:euroncap_aeb_c2c_v431 page:30 -->

CCRs/m/b CCFtap CCCscp CCFhos/hol
VVUT = 0km/h  *  
VVUT < VGVT for CCR 
Contact between VUT and GVT    
The GVT has left the path of the VUT  
* The VUT must not enter the path of the GVT to achieve the pass.

### 8.4.4 To ensure a safe testing environment in the CCFtap and CCCscp scenario, the test
laboratory may include an avoidance action by the robot in case the AEB/FCW system
fails to intervene (sufficiently). This action can be applied automatically when:

- The VUT reaches the latest position at which AEB intervention could be activated to
result in avoidance or significant mitigation (as applicable) and no intervention from the
AEB system is detected. OEMs can provide the latest position described above, in this
case, the labs may consider using them as reference to perform the avoidance action.
- Lateral separation between the VUT and GVT reaches ≤ 0m during / after AEB
intervention.
It is at the test laboratory’s discretion to select and use one of the options above to
ensure a safe testing environment. If the OEM feels the avoidance action is negatively
affecting the performance of their vehicle, they should consult with the test laboratory
and Euro NCAP secretariat.
### 8.4.5 For manual or automatic accelerator control, it needs to be assured that during automatic
brake the accelerator pedal does not result in an override of the system. The accelerator
pedal needs to be released when the initial test speed is reduced by 5 km/h. There shall
be no operation of other driving controls during the test, e.g. clutch or brake pedal.
### 8.4.6 The CCRs and CCCscp FCW system tests should be performed using a braking robot
reacting to the warning with a delay time of 1.2 seconds as per A.4 to account for driver
reaction time.
8.4.6.1 Braking will be applied that results in a maximum brake level of -4 m/s2 – 0.50 m/s2
when applied in a non-threat situation. The particular brake profile to be applied (pedal
application rate applied in 200ms (max. 400mm/s) and pedal force) shall be specified
by the manufacturer. When the brake profile provided by the manufacturer results in a
higher brake level than allowed, the iteration steps as described in ANNEX A will be
applied to scale the brake level to -4 m/s2 – 0.50 m/s2.
### 8.4.6.2 When no brake profile is provided, the default brake profile as described in ANNEX A
will be applied.
### 8.4.7 The ESS is evaluated at the Euro NCAP lab with input from the OEM to ensure proper
triggering of the system. The recommended testing procedure can be found in the
Technical Bulletin TB037.

Version 4.3.1
February 2024 26

## Source page 31
<!-- source_id:euroncap_aeb_c2c_v431 page:31 -->

### ANNEX A: BRAKE APPLICATION PROCEDURE

The braking input characterisation test determines the brake pedal displacement and
force necessary to achieve a vehicle deceleration typical of that produced by a typical
real-world driver in emergency situations.

A.1 Definitions
TBRAKE – The point in time where the brake pedal displacement exceeds 5mm.

T-6m/s2 – The point in time is defined as the first data point where filtered, zeroed and
corrected longitudinal acceleration data is less than -6m/s2.

T-2m/s², T-4m/s² - similar to T-6m/s².

A.2 Measurements
Measurements and filters to be applied as described in Chapter 4 of this protocol.

A.3 Brake Characterization Procedure

First perform the brake and tyre conditioning tests as described in 8.1.2 and 8.1.3. The
brake input characterisation tests shall be undertaken within 10 minutes after
conditioning the brakes and tyres.

A.3.1 Brake Displacement Characterisation Tests
• Push the brake pedal through the full extent of travel and release.
• Accelerate the VUT to a speed in excess of 85km/h. Vehicles with an automatic
transmission will be driven in D. For vehicles with a manual transmission select the
highest gear where the RPM will be at least 1500 at the 85km/h.
• Release the accelerator and allow the vehicle to coast. At a speed of 80 ± 1.0km/h
initiate a ramp braking input with a pedal application rate of 20±5mm/s and apply
the brake until a longitudinal acceleration of -7m/s2 is achieved. For manual
transmission vehicles, press the clutch as soon as the RPM drops below 1500. The
test ends when a longitudinal acceleration of -7m/s2 is achieved.
• Measure the pedal displacement and applied force normal to the direction of travel
of the initial stroke of the brake pedal, or as close as possible to normal as can be
repeatedly achieved.

Version 4.3.1
February 2024 27

## Source page 32
<!-- source_id:euroncap_aeb_c2c_v431 page:32 -->

A.3.1.1 Perform three consecutive test runs. A minimum time of 90 seconds and a maximum
time of 10 minutes shall be allowed between consecutive tests. If the maximum time of
10 minutes is exceeded, perform three brake stops from 72 km/h at approximately 0.3g.
• Using second order curve fit and the least squares method between T-2m/s², T-6m/s²,
calculate the pedal travel value corresponding to a longitudinal acceleration of -4
m/s² (=D4, unit is m). Use data of at least three valid test runs for the curve fitting.
• This brake pedal displacement is referred to as D4 in the next chapters.
• Using second order curve fit and the least squares method between T-2m/s², T-6m/s²,
calculate the pedal force value corresponding to a longitudinal acceleration of -4
m/s² (=F4, unit is N). Use data of at least three valid test runs for the curve fitting.
• This brake pedal force is referred to as F4 in the next chapters.

A.3.2 Brake Force Confirmation and Iteration Procedure
• Accelerate the VUT to a speed of 80+1km/h. Vehicles with an automatic
transmission will be driven in D. For vehicles with a manual transmission select the
highest gear where the RPM will be at least 1500 at the 80km/h.
• Apply the brake force profile as specified in B.4, triggering the input manually
rather than in response to the FCW. Determine the mean acceleration achieved
during the window from TBRAKE +1s TBRAKE +3s. If a mean acceleration outside the
range of -4-0.5m/s2 results, apply the following method to ratio the pedal force
applied.
F4new = F4original * (-4/mean acceleration), i.e. if F4original results in a mean
acceleration of -5m/s2, F4new = F4original * -4 / -5
• Repeat the brake force profile with this newly calculated F4, determine the mean
acceleration achieved and repeat the method as necessary until a mean acceleration
within the range of -4-0.5m/s2 is achieved.
A.3.2.1 Three valid pedal force characteristic tests (with the acceleration level being in the range
as specified) are required. A minimum time of 90 seconds and a maximum time of 10
minutes shall be allowed between consecutive tests. If the maximum time of 10 minutes
is exceeded, perform three brake stops from 72 km/h at approximately 0.3g.
• before restarting the brake pedal force characterisation tests. This brake pedal force
is referred as F4 in the next chapters.

Version 4.3.1
February 2024 28

## Source page 33
<!-- source_id:euroncap_aeb_c2c_v431 page:33 -->

A.4 Brake Application Profile
• Detect TFCW during the experiment in real-time.
• Release the accelerator at TFCW + 1 s.
• Perform displacement control for the brake pedal, starting at TFCW + 1.2 s with a
gradient of the lesser of 5 x D4 or 400mm/s (meaning the gradient to reach pedal
position D4 within 200ms, but capped to a maximum application rate of 400mm/s).
• Monitor brake force during displacement control and use second-order filtering with
a cut-off frequency between 20 and 100 Hz (online) as appropriate.
• Switch to force control, maintaining the force level, with a desired value of F4 when
i. the value D4 as defined in B.3 is exceeded for the first time,
ii. the force F4 as defined in B.3 is exceeded for the first time,
whichever is reached first.
• The point in time where position control is switched to force control is noted as
Tswitch.
• Maintain the force within boundaries of F4 ± 25% F4. A stable force level should
be achieved within a period of 200ms maximum after the start of force control.
Additional disturbances of the force over ± 25% F4 due to further AEB interventions
are allowed, as long as they have a duration of less than 200ms.
• The average value of the force between TFCW + 1.4s and the end of the test should
be in the range of F4 ± 10 N.

Version 4.3.1
February 2024 29

## Source page 34
<!-- source_id:euroncap_aeb_c2c_v431 page:34 -->

ANNEX B: Lane Change Path Definition

70km/h Lane Change Co-ordinates

Distance Time Curvature
(m) (s) X-Position (m) Y-Position (m) (1/m)
0 0 0 0 0
1 0,051 1 0,002 0,004
2 0,103 2 0,008 0,004
3 0,154 3 0,018 0,004
4 0,206 4 0,032 0,004
5 0,257 5 0,05 0,004
6 0,309 5,999 0,072 0,004
7 0,36 6,999 0,098 0,004
8 0,411 7,999 0,128 0,004
9 0,463 8,998 0,162 0,004
10 0,514 9,997 0,2 0,004
11 0,566 10,996 0,242 0,004
12 0,617 11,995 0,288 0,004
13 0,669 12,994 0,338 0,004
14 0,72 13,993 0,392 0,004
15 0,771 14,991 0,45 0,004
16 0,823 15,989 0,512 0,004
17 0,874 16,987 0,578 0,004
18 0,926 17,984 0,648 0,004
19 0,977 18,982 0,722 0,004
20 1,029 19,979 0,8 0,004
21 1,08 20,975 0,881 0,004
22 1,131 21,972 0,967 0,004
23 1,183 22,968 1,057 0,004
24 1,234 23,963 1,151 0,004
25 1,286 24,958 1,249 0,001
26 1,337 25,953 1,348 0
27 1,389 26,949 1,447 0
28 1,44 27,944 1,546 0
29 1,491 28,939 1,645 0
30 1,543 29,934 1,743 0
31 1,594 30,929 1,842 0
32 1,646 31,924 1,941 0
33 1,697 32,919 2,04 0
34 1,749 33,914 2,139 0

Version 4.3.1
February 2024 30

## Source page 35
<!-- source_id:euroncap_aeb_c2c_v431 page:35 -->

35 1,8 34,909 2,238 -0,001
36 1,851 35,904 2,336 -0,004
37 1,903 36,9 2,43 -0,004
38 1,954 37,896 2,521 -0,004
39 2,006 38,892 2,607 -0,004
40 2,057 39,889 2,69 -0,004
41 2,109 40,886 2,768 -0,004
42 2,16 41,883 2,843 -0,004
43 2,211 42,88 2,913 -0,004
44 2,263 43,878 2,98 -0,004
45 2,314 44,876 3,042 -0,004
46 2,366 45,875 3,101 -0,004
47 2,417 46,873 3,155 -0,004
48 2,469 47,872 3,206 -0,004
49 2,52 48,871 3,252 -0,004
50 2,571 49,87 3,295 -0,004
51 2,623 50,869 3,333 -0,004
52 2,674 51,868 3,368 -0,004
53 2,726 52,868 3,398 -0,004
54 2,777 53,868 3,425 -0,004
55 2,829 54,867 3,447 -0,004
56 2,88 55,867 3,466 -0,004
57 2,931 56,867 3,48 -0,004
58 2,983 57,867 3,491 -0,004
59 3,034 58,867 3,497 -0,004
60 3,086 59,867 3,5 0

Version 4.3.1
February 2024 31

## Source page 36
<!-- source_id:euroncap_aeb_c2c_v431 page:36 -->

50km/h Lane Change Co-ordinates

Distance Time Curvature
(m) (s) X-Position (m) Y-Position (m) (1/m)
0 0 0 0 0
1 0,072 1 0,004 0,008
2 0,144 2 0,015 0,008
3 0,216 3 0,035 0,008
4 0,288 3,999 0,062 0,008
5 0,36 4,999 0,096 0,008
6 0,432 5,998 0,138 0,008
7 0,504 6,997 0,188 0,008
8 0,576 7,995 0,246 0,008
9 0,648 8,993 0,311 0,008
10 0,72 9,99 0,384 0,008
11 0,792 10,987 0,465 0,008
12 0,864 11,983 0,553 0,008
13 0,936 12,978 0,649 0,008
14 1,008 13,973 0,753 0,008
15 1,08 14,967 0,864 0,008
16 1,152 15,96 0,983 0,006
17 1,224 16,952 1,109 0,001
18 1,296 17,944 1,235 0
19 1,368 18,936 1,361 0
20 1,44 19,928 1,487 0
21 1,512 20,92 1,613 0
22 1,584 21,912 1,739 0
23 1,656 22,904 1,865 0
24 1,728 23,896 1,991 0
25 1,8 24,888 2,117 0
26 1,872 25,88 2,243 0
27 1,944 26,872 2,369 0
28 2,016 27,864 2,495 -0,006
29 2,088 28,857 2,615 -0,008
30 2,16 29,85 2,728 -0,008
31 2,232 30,845 2,833 -0,008
32 2,304 31,84 2,93 -0,008
33 2,376 32,836 3,02 -0,008
34 2,448 33,833 3,102 -0,008
35 2,52 34,83 3,176 -0,008
36 2,592 35,828 3,243 -0,008
37 2,664 36,826 3,302 -0,008
38 2,736 37,825 3,353 -0,008
39 2,808 38,824 3,397 -0,008
40 2,88 39,823 3,433 -0,008

Version 4.3.1
February 2024 32

## Source page 37
<!-- source_id:euroncap_aeb_c2c_v431 page:37 -->

41 2,952 40,823 3,461 -0,008
42 3,024 41,822 3,482 -0,008
43 3,096 42,822 3,495 -0,008
44 3,168 43,822 3,5 0

Version 4.3.1
February 2024 33

## Source page 38
<!-- source_id:euroncap_aeb_c2c_v431 page:38 -->

ANNEX C: CCCscp Start from Stop

The gas pedal characterization test determines the gas pedal displacement and gas
pedal application velocity necessary to achieve a typical vehicle drive-away
acceleration in junction situations. In addition, the corresponding synchronization
timing between VUT and GVT is determined with the obtained speed profile.

C.1 Definitions

• TStart, Time when VUT filtered acceleration reaches [0.1] m/s2 TStart
(in CCCscp start from stop scenario)

• TEnd, time where VUT has travelled 2.9m. from the start position TEnd
(in CCCscp start from stop scenario)

• TAvg, average time value of TEnd from all the executed trials TAvg
(in CCCscp start from stop scenario)

C.2 Measurements
Measurements and filters to be applied as described in section 4 of this protocol.

C.3 Gas-Pedal characterization procedure
Via an iterative approach the gas pedal position has to be examined to achieve the
following:

• The longitudinal acceleration shall not exceed 1 m/s² before TStart + 0.5
seconds.
• The longitudinal acceleration shall not exceed 1.75 m/s² at any point and must
exceed 1m/s² from TStart + 1.25 until TEnd.

Execute the start action as trial (without the GVT) at least three times. TEnd of all runs
should be inside of an Interval of [0.1 s]. The results from the trials are used to
determine the gas pedal position and TAvg which constitute the parameters for the test.

Thereby, TAvg is used to trigger the start action of the VUT to ensure correct
synchronization to the GVT. With the known time that the VUT needs to reach the
impact location, it can be triggered by the approaching GVT and its known time to
reach the impact point location.

Version 4.3.1
February 2024 34

## Source page 39
<!-- source_id:euroncap_aeb_c2c_v431 page:39 -->

In the event that the above method does not satisfy the test requirements, or that the
intended vehicle to be tested (i.e. vehicle with base safety pack) is only offered with a
manual transmission and has CCCscp Start-from-Stop capabilities, the OEM shall
contact Euro NCAP to discuss an alternative approach.

Version 4.3.1
February 2024 35
