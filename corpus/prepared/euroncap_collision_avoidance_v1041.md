---
source_id: "euroncap_collision_avoidance_v1041"
title: "Euro NCAP Safety Assist Collision Avoidance Assessment Protocol"
publisher: "Euro NCAP"
version: "10.4.1"
language: "English"
source_url: "https://cdn.euroncap.com/cars/assets/euro_ncap_assessment_protocol_sa_collision_avoidance_v1041_fafe1dd418.pdf"
sha256: "911225776a14d31a830c48f7bcd5472425a0b0a53b44bc47fc42cc7ff899147f"
---

# Euro NCAP Safety Assist Collision Avoidance Assessment Protocol (10.4.1)

## Source page 1
<!-- source_id:euroncap_collision_avoidance_v1041 page:1 -->

### EUROPEAN NEW CAR ASSESSMENT PROGRAMME
(Euro NCAP)

### ASSESSMENT PROTOCOL – SAFETY ASSIST
### COLLISION AVOIDANCE

Implementation 2023

Version 10.4.1
February 2024

## Source page 2
<!-- source_id:euroncap_collision_avoidance_v1041 page:2 -->

Copyright 2024 ©Euro NCAP - This work is the intellectual property of Euro NCAP. Permission is granted for this
material to be shared for non-commercial, educational purposes, provided that this copyright statement appears
on the reproduced materials and notice is given that the copying is by permission of Euro NCAP. To disseminate
otherwise or to republish requires written permission from Euro NCAP.

## Source page 3
<!-- source_id:euroncap_collision_avoidance_v1041 page:3 -->

EUROPEAN NEW CAR ASSESSMENT PROGRAMME (Euro NCAP)

### ASSESSMENT PROTOCOL – SAFETY ASSIST – COLLISION AVOIDANCE

Table of Contents

1 INTRODUCTION .......................................................................................................... 2
2 METHOD OF ASSESSMENT ...................................................................................... 3
### 3 ASSESSMENT OF AEB CAR-TO-CAR SYSTEMS .................................................... 4

3.1 Introduction ........................................................................................................................... 4

3.2 Definitions .............................................................................................................................. 4

3.3 Criteria and Scoring .............................................................................................................. 6

3.4 Visualisation ......................................................................................................................... 13
### 6 ASSESSMENT OF LANE SUPPORT SYSTEMS ..................................................... 14

6.1 Introduction ......................................................................................................................... 14

6.2 Definitions ............................................................................................................................ 14

6.3 Criteria and Scoring ............................................................................................................ 14

6.4 Visualisation ......................................................................................................................... 19

## Source page 4
<!-- source_id:euroncap_collision_avoidance_v1041 page:4 -->

### 1 INTRODUCTION

The following protocol deals with the assessments made in the area of Safety Assist, in
particular for Lane Support Systems and Autonomous Emergency Braking Systems.

DISCLAIMER: Euro NCAP has taken all reasonable care to ensure that the information
published in this protocol is accurate and reflects the technical decisions taken by the
organisation. In the unlikely event that this protocol contains a typographical error or
any other inaccuracy, Euro NCAP reserves the right to make corrections and determine
the assessment and subsequent result of the affected requirement(s).

Version 10.4.1
February 2024

## Source page 5
<!-- source_id:euroncap_collision_avoidance_v1041 page:5 -->

### 2 METHOD OF ASSESSMENT

Unlike the assessment of protection offered in the event of a crash, the assessment of
Safety Assist functions does not require destructive testing of the vehicle. Assessment
of the Safety Assist functions is based both on performance requirements verified by
Euro NCAP. The intention is to promote standard fitment across the car volume sold in
the European Community in combination with good functionality for these systems,
where this is possible.

It is important to note that Euro NCAP only considers assessment of safety assist systems
that meet the fitment requirements for base safety equipment or dual rating (as defined
in the Vehicle Specification, Selection, Testing and Re-testing protocol). In addition to
the basic Euro NCAP assessment, additional information may be recorded that may be
added to the Euro NCAP assessment in the future.

Version 10.4.1
February 2024

## Source page 6
<!-- source_id:euroncap_collision_avoidance_v1041 page:6 -->

### 3 ASSESSMENT OF AEB CAR-TO-CAR SYSTEMS

### 3.1 Introduction
For the assessment of AEB Car-to-Car systems, three areas of assessment are
considered: the Autonomous Emergency Braking function, Forward Collision
Warning function and the Human Machine Interface (HMI). The FCW function is
only considered when the system provides dynamic brake support.

### 3.2 Definitions
### 3.2.1 General
Throughout this protocol the following terms are used:

Peak Braking Coefficient (PBC) – the measure of tyre to road surface friction based
on the maximum deceleration of a rolling tyre, measured using the American Society
for Testing and Materials (ASTM) E1136-10 (2010) standard reference test tyre, in
accordance with ASTM Method E 1337-90 (reapproved 1996), at a speed of
64.4km/h, without water delivery. Alternatively, the method as specified in UNECE
### R13-H.

Autonomous Emergency Braking (AEB) – braking that is applied automatically
by the vehicle in response to the detection of a likely collision to reduce the vehicle
speed and potentially avoid the collision.

Forward Collision Warning (FCW) – an audio-visual warning that is provided
automatically by the vehicle in response to the detection of a likely collision to alert
the driver.

Dynamic Brake Support (DBS) – a system that further amplifies the driver braking
demand in response to the detection of a likely collision to achieve a greater
deceleration than would otherwise be achieved for the braking demand in normal
driving conditions.

Autonomous Emergency Steering (AES) – steering that is applied automatically
by the vehicle in response to the detection of a likely collision to steer the vehicle
around the vehicle in front to avoid the collision.

Emergency Steering Support (ESS) – a system that supports the driver steering
input in response to the detection of a likely collision to alter the vehicle path and
potentially avoid a collision.

Vehicle under test (VUT) – means the vehicle tested according to this protocol with
a pre-crash collision mitigation or avoidance system on board

Vehicle width – the widest point of the vehicle ignoring the rear-view mirrors, side
marker lamps, tyre pressure indicators, direction indicator lamps, position lamps,
flexible mud-guards and the deflected part of the tyre side-walls immediately above
the point of contact with the ground.

Global Vehicle Target (GVT) – means the vehicle target used in this protocol as
defined in ISO 19206-3:2021

Version 10.4.1
February 2024

## Source page 7
<!-- source_id:euroncap_collision_avoidance_v1041 page:7 -->

Time To Collision (TTC) – means the remaining time before the VUT strikes the
GVT, assuming that the VUT and GVT would continue to travel with the speed it is
travelling.

TAEB – means the time where the AEB system activates. Activation time is
determined by identifying the last data point where the filtered acceleration signal is
below -1 m/s2, and then going back to the point in time where the acceleration first
crossed -0.3 m/s2

TFCW – means the time where the audible warning of the FCW starts. The starting
point is determined by audible recognition

Vimpact – means the speed at which the VUT hits the GVT

Vrel_impact – means the relative speed at which the VUT hits the GVT by
subtracting the velocity of the GVT from Vimpact at the time of collision
Driver Intention Monitoring system (DIM) – means a system that is effective at
distinguishing intentional from unintentional lane crossing and suppressing
undesired interventions and/or warnings.
### 3.2.2 Test Scenarios

Car-to-Car Rear Stationary (CCRs) – a collision in which a vehicle travels
forwards towards another stationary vehicle and the frontal structure of the vehicle
strikes the rear structure of the other.

Car-to-Car Rear Moving (CCRm) – a collision in which a vehicle travels forwards
towards another vehicle that is travelling at constant speed and the frontal structure
of the vehicle strikes the rear structure of the other.

Car-to-Car Rear Braking (CCRb) – a collision in which a vehicle travels forwards
towards another vehicle that is travelling at constant speed and then decelerates, and
the frontal structure of the vehicle strikes the rear structure of the other.

Car-to-Car Front Turn-Across-Path (CCFtap) – a collision in which a vehicle
turns across the path of an oncoming vehicle travelling at constant speed, and the
frontal structure of the vehicle strikes the front structure of the other.

Car-to-Car Crossing Straight Crossing Path (CCCscp) – a collision in which a
vehicle travels forwards along a straight path across a junction, towards a vehicle
crossing the junction on a perpendicular path. The frontal structure of the vehicle
under test strikes the side of the other vehicle.

Car-to-Car Front Head-On Straight (CCFhos) – a collision where a vehicle is
travelling along a straight path within its defined lane and strikes another vehicle
travelling in the opposite direction, which has drifted into the same lane as the
original vehicle. The frontal structure of the vehicle strikes the frontal structure of
the other.

Car-to-Car Front Head-On Lane change (CCFhol) – a collision where a vehicle
is travelling along a straight path within its defined lane and strikes another vehicle
travelling in the opposite direction which has intentionally moved into the lane of
the original vehicle to attempt an overtake. The frontal structure of the vehicle
strikes the frontal structure of the other.

Version 10.4.1
February 2024

## Source page 8
<!-- source_id:euroncap_collision_avoidance_v1041 page:8 -->

### 3.3 Criteria and Scoring
To be eligible for scoring points in AEB Car-to-Car, the AEB and/or FCW system
must:
- Not automatically switch off at a speed below 130km/h.
- Needs to be default ON at the start of every journey and deactivation of the
system should not be possible with a momentary single push on a button.
- The audible component of the FCW system (if applicable) needs to be loud
and clear.
Additionally, for the AEB CCRm scenario points for this scenario are awarded only
when the following precondition is met:
- Evidence is provided by the OEM to demonstrate the system is capable of
similar performance when tested in the CCRm scenario with a test speed of
130km/h and GVT speed of 70km/h, as with an 80km/h test speed with a
20km/h GVT speed (for all overlaps). Similar performance in considered
within one colour band difference as per 4.3.2.
Additionally, for the AEB CCRs scenario points for this scenario are awarded only
when the following preconditions are met:
- Whiplash score for the front seat is at least rated as “Good”.
- Full avoidance needs to be achieved for test speeds up to and including 20
km/h for all overlap situations, which is verified by one randomly selected
test point.

### 3.3.1 Assessment Criteria
For CCRs (both AEB and FCW), CCRb, CCFhos, CCFhol and CCCscp tests the
assessment criteria used is Vimpact. For CCRm tests the assessment criteria used is
Vrel impact. For CCFtap tests the assessment criteria is collision avoidance.
Alternatively, for CCRs FCW system tests @ -50% overlap (50% for RHD vehicles)
where performance does not result in full avoidance, the manufacturer has the option
to demonstrate to Euro NCAP at the test laboratory that their (driver initiated) ESS
system will function to avoid the collision by steering support. Euro NCAP has
elaborated a test procedure for ESS, which provisions can be found in TB 037.

### 3.3.2 Car-to-Car Rear
A maximum of 3.5 points is available for AEB/AES CCR. The scoring is based on
normalized scores of the AEB and FCW/AES functions, assessed in the CCRs,
CCRm and CCRb scenarios.
For each test point the result is given a colour based on the following tables. For the
purpose of these tables, CCRb tests are considered to be equivalent to a CCRs test
with a 50km/h VUT test speed.

Version 10.4.1
February 2024

## Source page 9
<!-- source_id:euroncap_collision_avoidance_v1041 page:9 -->

80 km/h
75 km/h
70 km/h
65 km/h
60 km/h [km/h] 55 km/h
50 km/h
Speed 45 km/h
Test 40 km/h
35 km/h
VUT 30 km/h
25 km/h
20 km/h
15 km/h
10 km/h

0 10 20 30 40 50 60 70 80

CCRs and CCRbImpact Speed [km/h]

130 & 80 km/h
75 km/h
70 km/h
65 km/h [km/h] 60 km/h
55 km/h
Speed 50 km/h
Test 45 km/h
40 km/h
VUT 35 km/h
30 km/h

0 10 20 30 40 50 60 70 80

CCRm Relative Impact Speed [km/h]

To aid understanding, the following table illustrates the speed range for each colour in a
CCRs and CCRb test with a VUT test speed of 50km/h.

Colour Impact speed range (km/h)
Green 0 < vimpact < 5
Yellow 5 ≤ vimpact < 15
Orange 15 ≤ vimpact < 30
Brown 30 ≤ vimpact < 40
Red 40 ≤ vimpact

For the CCRs and CCRm scenarios, the total score for all five grid points per test speed
is calculated as a percentage of the maximum achievable score per test speed, which is

Version 10.4.1
February 2024

## Source page 10
<!-- source_id:euroncap_collision_avoidance_v1041 page:10 -->

then multiplied by the points available for this test speed. It should be noted that the
100% overlap score is double counted.

𝑠𝑐𝑜𝑟𝑒 𝑎𝑡 [−50%] + 𝑠𝑐𝑜𝑟𝑒 𝑎𝑡 [−75%] + (𝑠𝑐𝑜𝑟𝑒 𝑎𝑡 [100%] × 2) + 𝑠𝑐𝑜𝑟𝑒 𝑎𝑡 [75%] + 𝑠𝑐𝑜𝑟𝑒 𝑎𝑡 [50%]
6

For each predicted colour the following scaling is applied to the grid point:
Green 1.000
Yellow 0.750
Orange 0.500
Brown 0.250
Red 0.000
The points available for the different CCR grid points and/or scenarios are shown in the
table below:

Test Speed AEB FCW
(km/h) CCRs CCRm CCRb CCRs
10 1.000
15 2.000
20 2.000
25 2.000
30 2.000 1.000
35 2.000 1.000
40 1.000 1.000
45 1.000 1.000
50 1.000 1.000 4 x 1.000
55 1.000 1.000
60 1.000 1.000
65 2.000 1.000
70 2.000 1.000
75 2.000 1.000
80 2.000 1.000
Total 14.000 15.000 4.000 6.000
Scenario 1.000 1.000 1.000 0.500
Points

### 3.3.2.1 Correction factors
The data provided by the manufacturer for CCRs and CCRm is scaled using two
correction factors, one for AEB and one for FCW/AES, which are calculated based
on a number of verification tests performed. The vehicle sponsor will fund 15
verification tests, 10 for AEB and 5 for FCW/AES where applicable. The vehicle
manufacturer has the option of sponsoring up to 10 additional verification tests for
AEB and 5 for FCW/AES.
The verification points are randomly selected grid points, distributed in line with the
predicted colour distribution (excluding red points).
The actual tested total score of the verification test points is divided by the predicted
total score of these verification test points. This is called the correction factor, which
can be lower or higher than 1.

Version 10.4.1
February 2024

## Source page 11
<!-- source_id:euroncap_collision_avoidance_v1041 page:11 -->

𝐴𝑐𝑡𝑢𝑎𝑙 𝑡𝑒𝑠𝑡𝑒𝑑 𝑠𝑐𝑜𝑟𝑒
𝐶𝑜𝑟𝑟𝑒𝑐𝑡𝑖𝑜𝑛 𝐹𝑎𝑐𝑡𝑜𝑟=
𝑃𝑟𝑒𝑑𝑖𝑐𝑡𝑒𝑑 𝑠𝑐𝑜𝑟𝑒

The correction factor is used to calculate the CCRs and CCRm scores for the AEB
and FCW/AES function scores. The final CCRs and CCRm scores for AEB and
FCW/AES can never exceed 100% (3.0 and 0.5 points respectively) regardless of
the correction factor.

### 3.3.2.2 Impact speed tolerance
As test results can be variable between labs and in-house tests and/or simulations a
2 km/h tolerance to the impact speeds of the verification test is applied. The tolerance
is applied in both directions, meaning that when a tested point scores better than
predicted, but within tolerance, the predicted result is applied.
The tolerance only applies to verify whether the predicted colour of the tested
verification point is correct. When, including tolerance, the colour is not in line with
the prediction, the true colour of the test point will be determined by comparing the
actual measured impact speed with the colour band in section 3.3.2 without applying
a tolerance to the impact speed.
As an example, the accepted impact speed ranges for the 50km/h CCRs and CCRb
tests are as follows:

Prediction Impact speed range [km/h] Accepted range [km/h]
Green 0 ≤ vimpact < 5 0 ≤ vimpact < 7
Yellow 5 ≤ vimpact < 15 3 ≤ vimpact < 17
Orange 15 ≤ vimpact < 30 13 ≤ vimpact < 32
Brown 30 ≤ vimpact < 40 28 ≤ vimpact < 42
Red 40 ≤ vimpact excluded

### 3.3.3 Car-to-Car Front turn across path
A maximum of 1 point is available for AEB CCFtap. A normalised score is
calculated based on the number of scenarios (out of 9) where the vehicle itself
avoided the collision. This normalised score is multiplied with the available points
for CCFtap.

CCFtap Test Speed
GVT @ 30km/h GVT @ 45km/h GVT @ 60km/h
10 km/h 1.000 1.000 1.000
15 km/h 1.000 1.000 1.000
20 km/h 1.000 1.000 1.000
Total 9.000
Scenario Points 1.000

### 3.3.4 Car-to-car crossing straight crossing path
A maximum of 2 points is available for AEB CCCscp. A normalised score is
calculated based on the results of the 30 test speed combinations.

Version 10.4.1
February 2024

## Source page 12
<!-- source_id:euroncap_collision_avoidance_v1041 page:12 -->

CCCscp AEB
Test Speed GVT Speed
20km/h 30km/h 40km/h 50km/h 60km/h
Start from stop 0.500 0.500 0.500 0.500 0.500
20 km/h 1.000 0.250 0.250 0.250 0.250
30 km/h 1.000 1.000 0.250 0.250 0.250
40 km/h 1.000 1.000 1.000 0.250 0.250
50 km/h 1.000 1.000 1.000 1.000 0.250
60 km/h 1.000 1.000 1.000 1.000 1.000
Total 20.000
Scenario 2.000
Points

A maximum of 1 point is available for FCW CCCscp. A normalised score is
calculated based on the results of the 15 test speed combinations.
Where the AEB system avoided the collision, the points are automatically awarded
for the corresponding FCW test.

CCCscp FCW
Test Speed GVT Speed
20km/h 30km/h 40km/h 50km/h 60km/h
40 km/h 1.000 1.000 1.000 0.250 0.250
50 km/h 1.000 1.000 1.000 1.000 0.250
60 km/h 1.000 1.000 1.000 1.000 1.000
Total 12.75
Scenario 1.000
Points

The criteria for scoring points for both AEB and FCW are:
- Where the VUT test speed is ≤30km/h (including start from stop) points are
scored a pass/fail criteria based on collision avoidance.

- Where the VUT test speed is ≥40km/h:
• Full points are awarded per test where the vehicle’s AEB/FCW
system activates, and the collision is avoided.
• Half points are awarded per test where the vehicle’s AEB/FCW
system activates, mitigating the collision speed by ≥30km/h.
- Where a test speed combination is avoided by AEB, the points are
automatically awarded for the corresponding FCW test.

Version 10.4.1
February 2024

## Source page 13
<!-- source_id:euroncap_collision_avoidance_v1041 page:13 -->

60

50
[km/h]

40
Speed
100% of sub-points 30 Test
50% of sub-points
VUT
### 20 No sub-points

0 10 20 30 40 50 60

CCCscp Impact Speed [km/h]

### 3.3.5 Car-to-car front head on
A maximum of 1 point is available for AEB CCFhos/CCFhol .
The OEM must demonstrate, by means of a dossier, that in the following test
scenarios the vehicle’s AEB system will activate, mitigating the impact speed of the
collision. The OEM must demonstrate that the system achieves the minimum
mitigation required to score points across the specified speed range for each test
scenario.
For each test scenario:
- 0.25 points are awarded if a speed reduction ≥20km/h is achieved.
- 0.125 points are awarded where 10km/h ≤ speed reduction < 20km/h is
achieved.

Car-to-Car Head On
Test Speed Points
Scenario
VUT Test Target (speed reduction ≥20km/h)
50 km/h 50 km/h 0.250
CCFhos
70 km/h 70 km/h 0.250
50 km/h 50 km/h 0.250
CCFhol
70 km/h 70 km/h 0.250
Total 1.000
Scenario Points 1.000

### 3.3.6 Human Machine Interface (HMI)
A maximum of 0.5 points are available for HMI. A normalised HMI score is
calculated based on the two criteria below.
Points can be achieved for the following:
- Supplementary warning for the FCW system: 1 point
In addition to the required audio-visual warning, a more sophisticated warning like
head-up display, belt jerk, or any other haptic feedback (with an exception to brake
jerk, see below note) is awarded when it is issued at a TTC > 1.2s (applying to FCW
CCRs 55~80km/h including all overlaps). Alternatively, it will be awarded if all

Version 10.4.1
February 2024

## Source page 14
<!-- source_id:euroncap_collision_avoidance_v1041 page:14 -->

CCR scenarios are avoided up to 80 kph by AEB only.
NOTE: The supplementary warning point is not applicable to AEB only systems
NOTE: Additional requirements for using braking as a supplementary warning in
CCR scenarios > 40kph relative speed:
• A brake jerk is accepted when issued ≥0.5s before main AEB intervention,
with a jerk of ≥ 10m/s3, reaching a deceleration more than 0.5m/s² (or
lasting a minimum duration of 50 ms) OR
• A partial deceleration step is accepted when a constant acceleration ≤ -2m/s
² is seen for a duration of ≥0.5s before main AEB intervention.

- Reversible pre-tensioning of the belt in the pre-crash phase or ESS: 1 point
When the system detects a critical situation that can possibly lead to a crash, the belt
can already be pre-tensioned to prepare for the oncoming impact.
As an alternative way to score 1 point, the vehicle shall be equipped with ESS, for
which the system requirements and the testing procedure can be found in the
Technical Bulletin TB037.

### 3.3.7 Total AEB Car-to-Car Score
The total score in points is the weighted sum of the CCR scores, the CCFtap score,
the CCCscp scores, the CCFho scores and HMI. Where the scores are expressed as
percentages:

(𝐶𝐶𝑅𝑠 𝐴𝐸𝐵 𝑠𝑐𝑜𝑟𝑒 𝑥 𝐶𝐶𝑅 𝐴𝐸𝐵 𝐶𝑜𝑟𝑟𝑒𝑐𝑡𝑖𝑜𝑛 𝑓𝑎𝑐𝑡𝑜𝑟 𝑥 1.0)
+(𝐶𝐶𝑅𝑚 𝐴𝐸𝐵 𝑠𝑐𝑜𝑟𝑒 𝑥 𝐶𝐶𝑅 𝐴𝐸𝐵 𝐶𝑜𝑟𝑟𝑒𝑐𝑡𝑖𝑜𝑛 𝑓𝑎𝑐𝑡𝑜𝑟 𝑥 1.0)
+(𝐶𝐶𝑅𝑏 𝐴𝐸𝐵 𝑠𝑐𝑜𝑟𝑒 𝑥 1.0)
+(𝐶𝐶𝑅𝑠 𝐹𝐶𝑊 𝑠𝑐𝑜𝑟𝑒 𝑥 𝐶𝐶𝑅𝑠 𝐹𝐶𝑊 𝐶𝑜𝑟𝑟𝑒𝑐𝑡𝑖𝑜𝑛 𝑓𝑎𝑐𝑡𝑜𝑟 𝑥 0.5)
+(𝐶𝐶𝐹𝑡𝑎𝑝 𝑠𝑐𝑜𝑟𝑒 𝑥 1.0)
+(𝐶𝐶𝐶𝑠𝑐𝑝 𝐴𝐸𝐵 𝑠𝑐𝑜𝑟𝑒 𝑥 2.0)
+(𝐶𝐶𝐶𝑠𝑐𝑝 𝐹𝐶𝑊 𝑠𝑐𝑜𝑟𝑒 𝑥 1.0)
+(𝐶𝐶𝐹ℎ𝑜𝑠/ℎ𝑜𝑙 𝑠𝑐𝑜𝑟𝑒 𝑥 1.0)
+(𝐻𝑀𝐼 𝑠𝑐𝑜𝑟𝑒 𝑥 0.5)

= 𝑨𝑬𝑩 𝑪𝒂𝒓𝒕𝒐𝑪𝒂𝒓 𝒕𝒐𝒕𝒂𝒍 𝒔𝒄𝒐𝒓𝒆

Version 10.4.1
February 2024

## Source page 15
<!-- source_id:euroncap_collision_avoidance_v1041 page:15 -->

### 3.3.7.1 Scoring Example

AEB Car-to-car Points Correction Factor Percentage Score
### CCR AEB
CCRs 12 1.02 87.4 0.874 /1.000
CCRm 15 1.02 100 1.000 /1.000
CCRb 4 100 1.000 /1.000
### CCR FCW
CCRs 6 0.95 95% 0.475 /0.500
CCFtap 6 66.7 0.667 /1.000
CCCscp
### AEB 12.5 62.5 1.250 /2.000
### FCW 12.75 100 1.000 /1.000
CCFhol / hos 0.5 50 0.500 /1.000
### HMI 2 100 0.500 /0.500
Total 7.266 /9.000

### 3.4 Visualisation
The AEB Car-to-Car scores are presented separately using a coloured top view of
the scenario for the different overlap situations (where applicable); left overlap, full
overlap and right overlap. The colours used are based on the overlap scores
respectively, rounded to three decimal places.

Colour Verdict Applied to Total Score For sub Scores
Green ‘Good’ 6.751 – 9.000 points 75.0% - 100.0%
Yellow ‘Adequate’ 4.501 – 6.750 points 50.0% - 75.0%
Orange ‘Marginal’ 2.251 – 4.500 points 25.0% - 50.0%
Brown ‘Weak’ 0.001 – 2.250 points 00.0% - 25.0%
Red ‘Poor’ 0.000 points 00.0%

Version 10.4.1
February 2024

## Source page 16
<!-- source_id:euroncap_collision_avoidance_v1041 page:16 -->

### 4 ASSESSMENT OF LANE SUPPORT SYSTEMS

### 4.1 Introduction
Lane support systems are becoming increasingly widespread and Euro NCAP has
acknowledged their safety potential via the Euro NCAP Advanced award process
from 2010. From 2014, these systems are included in the Safety Assist score.
Euro NCAP has developed tests which complement any legislative requirements, to
be able to rate lane support systems in more detail.

### 4.2 Definitions

Emergency Lane Keeping (ELK) – default ON heading correction that is applied
automatically by the vehicle in response to the detection of the vehicle that is about
to drift beyond the edge of the road or into oncoming or overtaking traffic in the
adjacent lane.

Lane Keeping Assist (LKA) – heading correction that is applied automatically by
the vehicle in response to the detection of the vehicle that is about to drift beyond a
delineated edge line of the current travel lane.

Lane Departure Warning (LDW) – a warning that is provided automatically by
the vehicle in response to the vehicle that is about to drift beyond a delineated edge
line of the current travel lane.

Vehicle under test (VUT) – means the vehicle tested according to this protocol with
a Lane Keep Assist and/or Lane Departure Warning system.

Time To Collision (TTC) – means the remaining time before the VUT strikes the
GVT, assuming that the VUT and GVT would continue to travel with the speed it is
travelling.

Lane Edge – means the inner side of the lane marking or the road edge

Distance To Lane Edge (DTLE) – means the remaining lateral distance
(perpendicular to the Lane Edge) between the Lane Edge and most outer edge of the
tyre, before the VUT crosses Lane Edge, assuming that the VUT would continue to
travel with the same lateral velocity towards it.

Driver Intention Monitoring system (DIM) - means a system that is effective at
distinguishing intentional from unintentional lane crossing and suppressing
undesired interventions.

### 4.3 Criteria and Scoring
To be eligible for scoring points in Lane Support Systems, the vehicle must be
equipped with an ESC system that complies with UNECE Regulation 13H.
For any system, the driver must be able to override the intervention by the system.
### 4.3.1 Human Machine Interface (HMI)
A maximum of 0.50 HMI points can be achieved for one of the following:

Version 10.4.1
February 2024

## Source page 17
<!-- source_id:euroncap_collision_avoidance_v1041 page:17 -->

Lane Departure Warning 0.50 points
Any LDW system that issues a haptic warning clearly relating to the lateral control
of the vehicle noticeable by the driver (e.g. notable heading correction, steering
wheel vibration, etc.) before a DTLE of -0.2m is awarded when active at lateral
velocities up to at least 1m/s.
Blind Spot Monitoring 0.50 points
The vehicle is additionally equipped with a Blind Spot Monitoring system on both
sides of the vehicle to warn the driver of other vehicles present in the blind spot.

### 4.3.1.1 Blind spot monitoring
For the Blind spot monitoring tests, the assessment criteria used is the blind spot
information supplied in respect to the test target position.
For a pass to be awarded visual blind spot information must be provided
continuously when the front end of the test target is within the red areas shown in
red in the following diagram (NOTE: to avoid a collision, the virtual box around the
test target shall never exceed D):

Figure 4-1 Blind spot monitoring scenario assessment

Version 10.4.1
February 2024

## Source page 18
<!-- source_id:euroncap_collision_avoidance_v1041 page:18 -->

Version 10.4.1
February 2024

## Source page 19
<!-- source_id:euroncap_collision_avoidance_v1041 page:19 -->

### 4.3.2 Lane Keep Assist (LKA)
For LKA system tests, the assessment criteria used is the Distance to Lane Edge
### (DTLE).
The limit value for DTLE for LKA tests is set to -0.3m for testing against lines,
meaning that the LKA system must not permit the VUT to cross the inner edge of
the lane marking by a distance greater than 0.3m.
The available points per test are awarded based on a pass/fail basis where all tests
within the scenario and road marking combination need to be a pass. The points
available for the different LKA scenario and road marking combinations are detailed
in the table below:

LKA Scenario Road Marking Points
Dashed Line Single lane marking 0.25
Solid Line Single lane marking 0.25
Total 0.50

### 4.3.3 Emergency Lane Keeping (ELK)

### 4.3.3.1 To be eligible for scoring points in ELK, the ELK part of the LSS system needs to
be default ON at the start of every journey and deactivation of the system should not
be possible with a momentary single push on a button.

### 4.3.3.2 For ELK Road Edge and Solid line tests, the assessment criteria used is the Distance
to Lane Edge (DTLE).

4.3.3.3 The limit value for DTLE for ELK Road Edge tests is set to -0.1m, meaning that the
vehicle is only allowed to have a part of the front wheel outside of the road edge.
The limit value for DTLE for ELK Solid line tests is set to -0.3m for testing against
lines, meaning that the ELK system must not permit the VUT to cross the inner edge
of the lane marking by a distance greater than 0.3m.

### 4.3.3.4 For ELK tests with oncoming and overtaking vehicles, the assessment criteria used
is “no impact”, meaning that the VUT is not allowed to contact the overtaking or
oncoming vehicle target at any time during the test.
The points for ELK Oncoming and ELK Overtaking Unintentional may be achieved
using a system where LKA dashed line is implemented as an ELK functionality
(default-on) and the LKA dashed line tests fulfils all LKA dashed lane criteria,
provided that either:
• The system features a Driver Intention Monitoring (DIM) with subsequent
suppression of undesired intervention, OR
• The steering torque applied by the driver to override the system is <=3.5 Nm
For both cases, the OEM shall provide a dossier that includes a system overview
and compelling evidence demonstrating how the system is effective at eliminating
or mitigating driver acceptance issues associated with lateral control. For DIM,
specific provisions for the dossier are outlined in 4.3.3.5.

Version 10.4.1
February 2024

## Source page 20
<!-- source_id:euroncap_collision_avoidance_v1041 page:20 -->

### 4.3.3.5 For the evaluation of Driver Intention Monitoring (DIM) system, Euro NCAP
requires a dossier from the OEM containing a detailed technical assessment. The
dossier shall contain, as minimum:
### 1. Overview of the DIM System operating principle and its strategy/logic to
determine driver ‘intention’, including a list of the Indirect/Direct input
variables and their inter-dependency for suppressing undesired LKA
interventions.
2. System Failsafe strategies in which DIM system is overruled e.g.,
o To avoid a crash with a threat on a collision course
o When a driver is deemed incapacitated
### 3. Information describing naturalistic driving in which lane marking crossing/lane
changing manoeuvring typically occurs for the vehicle, and associated driver
indicator usage
### 4. Evidence of the effectiveness of the system at suppressing undesirable LKA
interventions and promoting driver acceptance
### 5. Any other information the OEM deems relevant to support their application

### 4.3.3.6 The available points per test are awarded based on a pass/fail basis where all tests
within the scenario and road marking combination need to be a pass. The points
available for the different ELK scenario and road marking combinations are detailed
in the table below:

ELK Scenario Road Marking Points
Road Edge Road edge only 0.25
Dashed centre line & no line next to road edge 0.25
Solid Line Fully marked lane (non-tested side dashed or solid) 0.50
Oncoming Vehicle Fully marked lanes 0.50
Overtaking Vehicle Fully marked lanes 0.50
Total 2.00

Version 10.4.1
February 2024

## Source page 21
<!-- source_id:euroncap_collision_avoidance_v1041 page:21 -->

### 4.3.4 Total LSS Score
The total score in points is the sum of the HMI score, LKA score and ELK score.

LSS Function Points
### HMI 0.50
### LKA 0.50
### ELK 2.00
Total 3.00

### 4.4 Visualisation
The LSS scores are presented separately using a colour for the different LSS
functions; HMI, LKA and ELK. The colours used are based on the function scores
respectively, rounded to three decimal places.
Colour Verdict Applied to Total Score For sub Scores
Green ‘Good’ 2.251 – 3.000 points 75.0% - 100.0%
Yellow ‘Adequate’ 1.501 – 2.250 points 50.0% - 75.0%
Orange ‘Marginal’ 0.751 – 1.500 points 25.0% - 50.0%
Brown ‘Weak’ 0.001 – 0.750 points 00.0% - 25.0%
Red ‘Poor’ 0.000 points 00.0%

Version 10.4.1
February 2024
