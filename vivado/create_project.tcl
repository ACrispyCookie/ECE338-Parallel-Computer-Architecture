# Create the Vivado project and regenerate the gpgpu_system block design.
# Run with:
#   vivado -mode batch -source vivado/create_project.tcl

source [file join [file dirname [info script]] "config.tcl"]

create_project $PROJECT_NAME $PROJECT_DIR -part $FPGA_PART -force
set_property board_part $BOARD_PART [current_project]
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property default_lib xil_defaultlib [current_project]

# Keep source ordering deterministic. Add headers first, then leaf/module RTL.
set rtl_files [list]
foreach pattern [list \
    [file join $SRC_DIR "*.vh"] \
    [file join $SRC_DIR "sp" "*.v"] \
    [file join $SRC_DIR "memory" "*.v"] \
    [file join $SRC_DIR "*.v"] \
] {
    foreach f [lsort [glob -nocomplain $pattern]] {
        lappend rtl_files $f
    }
}

if {[llength $rtl_files] == 0} {
    error "No RTL files found under $SRC_DIR"
}

add_files -norecurse $rtl_files
set_property include_dirs [list $SRC_DIR] [current_fileset]

# constraints.xdc contains the three exported LED/status ports from the wrapper.
if {[file exists $XDC_FILE]} {
    add_files -fileset constrs_1 -norecurse $XDC_FILE
} else {
    puts "WARNING: constraints file not found: $XDC_FILE"
}

# Testbench is optional for the Vivado project, but useful for GUI/XSim.
set tb_file [file join $TEST_DIR "tb_GPGPU_e2e.v"]
if {[file exists $tb_file]} {
    add_files -fileset sim_1 -norecurse $tb_file
    set_property top tb_GPGPU_e2e [get_filesets sim_1]
    set_property -name {xsim.simulate.xsim.more_options} \
        -value "-testplusarg TEST_ROOT=$TEST_DIR/tests" \
        -objects [get_filesets sim_1]
}

# Recreate the block design from Tcl.
source [file join [file dirname [info script]] "create_bd_gpgpu_system.tcl"]

# Generate products and wrapper.
set bd_file [get_files [file join $PROJECT_DIR "$PROJECT_NAME.srcs" "sources_1" "bd" $BD_NAME "$BD_NAME.bd"]]
generate_target all $bd_file
make_wrapper -files $bd_file -top

set wrapper_file [file join $PROJECT_DIR "$PROJECT_NAME.gen" "sources_1" "bd" $BD_NAME "hdl" "${BD_NAME}_wrapper.v"]
if {![file exists $wrapper_file]} {
    error "Expected wrapper was not generated: $wrapper_file"
}
add_files -norecurse $wrapper_file

set_property top $TOP_NAME [current_fileset]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

save_project
puts "INFO: Created deterministic Vivado project: [file join $PROJECT_DIR $PROJECT_NAME.xpr]"
