/* ARM-mode wrapper for G214 OBJDLL OBJ_Time_getTotalOffset.
 * Original prologue is copied exactly into original_trampoline. The linker
 * resolves original_resume to entry+8. No new imports or absolute data pointers.
 */
.syntax unified
.arm
.section .text.entry,"ax",%progbits
.global nz_entry
.type nz_entry,%function
nz_entry:
    push {r4, r5, r6, r7, r8, lr}
    mov r4, r0
    mov r5, r1
    bl original_trampoline
    cmp r0, #0
    bne 1f
    mov r0, r4
    mov r1, r5
    /* Stock CE code uses four-byte stack alignment at some call sites.
     * Give the freestanding AAPCS C function eight-byte alignment explicitly.
     */
    mov r6, sp
    bic sp, sp, #7
    bl nz_apply
    mov sp, r6
    mov r0, #0              /* preserve the stock successful status, not 1 */
1:
    pop {r4, r5, r6, r7, r8, pc}
.size nz_entry, .-nz_entry

.type original_trampoline,%function
original_trampoline:
    push {r4, r5, lr}       /* stock bytes: 30 40 2d e9 */
    mov r4, r1             /* stock bytes: 01 40 a0 e1 */
    b original_resume
.size original_trampoline, .-original_trampoline
