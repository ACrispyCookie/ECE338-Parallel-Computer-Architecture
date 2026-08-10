addi x5,x31,0
slli x6,x5,0x6
lui x2,0x2
addi x2,x2,0 # 2000 <__stack_top>
sub x2,x2,x6
jal x1,1c <kernel_main>
jal x0,18 <_start+0x18>
addi x15,x31,0
lui x14,0x0
addi x14,x14,64 # 40 <__gpu_args_base>
lw x14,0(x14)
slli x13,x15,0x2
slli x15,x15,0x2
add x12,x14,x15
add x13,x14,x13
lw x13,4(x13)
lw x12,0(x12)
add x14,x14,x15
sub x15,x13,x12
sw x15,132(x14)
jalr x0,0(x1)
