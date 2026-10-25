// manual-DecompCreate.java - decompile functions at the given entry addresses,
// disassembling and creating them in memory first when Ghidra's analysis left
// them undefined. Use with -readOnly: the in-memory changes are never saved.
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class manual_DecompCreate extends GhidraScript {
    public void run() throws Exception {
        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);
        for (String arg : getScriptArgs()) {
            for (String part : arg.split(",")) {
                if (part.isBlank()) continue;
                Address a = toAddr(part.trim().replaceFirst("^0x", ""));
                Function f = getFunctionAt(a);
                if (f == null) {
                    new DisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
                    f = createFunction(a, null);
                    println("CREATED " + (f == null ? "FAILED" : f.getName()) + " @ " + a);
                }
                if (f == null) continue;
                DecompileResults r = ifc.decompileFunction(f, 120, monitor);
                println("FUNCTION " + f.getName() + " @ " + f.getEntryPoint());
                println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "DECOMPILE FAILED");
            }
        }
        ifc.dispose();
    }
}
