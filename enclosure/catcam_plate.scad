// CatCam sensor plate
// Flat mounting plate for a Raspberry Pi Camera v1.3 and an HC-SR501 PIR sensor.
//
// - Both boards mount on the BACK of the plate on standoffs (M2 screws + nuts).
// - The camera lens and the PIR dome poke through openings in the plate.
// - Optional corner legs hold the plate off the wall/shelf, leaving room for the
//   PIR's jumper wires and the camera ribbon behind it.
//
// Print orientation: FRONT FACE DOWN on the build plate (as modelled, front = z 0).
// The standoffs and legs grow upward, so no supports are needed.
//
// All dimensions are in mm. MEASURE YOUR BOARDS: the values marked (verify) come
// from typical specs, and cheap PIR boards in particular vary between batches.

/* [Plate] */
plate_t     = 3;     // plate thickness
margin      = 11;    // border around the boards (must clear the legs)
gap         = 8;     // space between camera and PIR boards
corner_r    = 3;     // plate corner rounding

/* [Resin tolerance] */
hole_comp   = 0.2;   // added to hole diameters (resin holes print slightly small)

/* [Camera - Pi Camera v1.3] */
cam_w            = 25;    // board width
cam_h            = 24;    // board height
cam_hole_inset   = 2;     // hole centers from the top and side edges
cam_hole_dx      = 21;    // horizontal hole spacing
cam_hole_dy      = 12.5;  // vertical hole spacing (from the top row down)
cam_lens_from_top = 9.5;  // lens center from the board's top edge (verify)
cam_lens_open    = 9.5;   // square opening for the 8.5 mm lens housing
cam_standoff_h   = 3;     // board-to-plate gap (clears the front-side connector)

/* [PIR - HC-SR501] */
pir_w            = 32;    // board width (verify)
pir_h            = 24;    // board height (verify)
pir_hole_dx      = 28;    // spacing of the two mounting holes (verify)
pir_dome_d       = 23.2;  // opening for the Fresnel dome (verify)
pir_standoff_h   = 2.5;   // board-to-plate gap = dome flange height (verify)

/* [Board screws (M2)] */
m2_clear_d  = 2.2;   // M2 clearance hole
standoff_d  = 5;     // camera standoff outer diameter
pir_standoff_d = 4.4; // PIR standoffs are slimmer so they clear the dome opening

/* [Mounting legs] */
use_legs    = true;
leg_h       = 25;    // leg height behind the plate (room for Dupont plugs + ribbon)
leg_d       = 9;     // leg diameter
leg_inset   = 5.5;   // leg center from the plate edges
mount_d     = 3.4;   // mounting screw hole (M3 / #4)
csk_d       = 6.5;   // countersink diameter on the front face (0 = none)

$fn = 64;

// ---------------------------------------------------------------------------
// Layout (front-view coordinates: X to the right, Y up, as seen from the front)

inner_h = max(cam_h, pir_h);
plate_w = 2 * margin + cam_w + gap + pir_w;
plate_h = 2 * margin + inner_h;

cam_x0 = margin;                          // camera board bottom-left (front view)
cam_y0 = margin + (inner_h - cam_h) / 2;
pir_x0 = margin + cam_w + gap;            // PIR board bottom-left (front view)
pir_y0 = margin + (inner_h - pir_h) / 2;

// The model's front face is at z = 0 and the back faces +z. Seen from the front
// (looking from -z), model +X points LEFT, so front-view X is mirrored here.
function fx(x) = plate_w - x;

cam_lens = [cam_x0 + cam_w / 2, cam_y0 + cam_h - cam_lens_from_top];
cam_holes = [
    for (dx = [0, cam_hole_dx], dy = [0, cam_hole_dy])
        [cam_x0 + cam_hole_inset + dx, cam_y0 + cam_h - cam_hole_inset - dy]
];

pir_center = [pir_x0 + pir_w / 2, pir_y0 + pir_h / 2];
pir_holes = [
    for (s = [-1, 1]) [pir_center[0] + s * pir_hole_dx / 2, pir_center[1]]
];

leg_pts = [
    for (x = [leg_inset, plate_w - leg_inset], y = [leg_inset, plate_h - leg_inset])
        [x, y]
];

echo(str("Plate size: ", plate_w, " x ", plate_h, " mm (Mars 2 build area 129 x 80)"));
echo(str("Total depth with legs: ", use_legs ? plate_t + leg_h : plate_t, " mm"));

// ---------------------------------------------------------------------------

module at(p, z = 0) { translate([fx(p[0]), p[1], z]) children(); }

module rounded_plate() {
    linear_extrude(plate_t)
        offset(r = corner_r) offset(delta = -corner_r)
            square([plate_w, plate_h]);
}

module standoff(h, d) {
    cylinder(h = plate_t + h, d = d);
}

module body() {
    rounded_plate();
    for (p = cam_holes) at(p) standoff(cam_standoff_h, standoff_d);
    for (p = pir_holes) at(p) standoff(pir_standoff_h, pir_standoff_d);
    if (use_legs) for (p = leg_pts) at(p) cylinder(h = plate_t + leg_h, d = leg_d);
}

module cutouts() {
    // Camera lens housing (square)
    at(cam_lens, -1)
        translate([-(cam_lens_open + hole_comp) / 2, -(cam_lens_open + hole_comp) / 2, 0])
            cube([cam_lens_open + hole_comp, cam_lens_open + hole_comp, plate_t + 2]);

    // PIR dome
    at(pir_center, -1) cylinder(h = plate_t + 2, d = pir_dome_d + hole_comp);

    // M2 board screw holes, straight through the plate and standoffs
    for (p = concat(cam_holes, pir_holes))
        at(p, -1) cylinder(h = plate_t + max(cam_standoff_h, pir_standoff_h) + 2,
                           d = m2_clear_d + hole_comp);

    // Mounting holes through the legs, countersunk on the front face
    if (use_legs) for (p = leg_pts) {
        at(p, -1) cylinder(h = plate_t + leg_h + 2, d = mount_d + hole_comp);
        if (csk_d > mount_d)
            at(p, -0.01) cylinder(h = (csk_d - mount_d) / 2, d1 = csk_d, d2 = mount_d);
    }
}

difference() {
    body();
    cutouts();
}
