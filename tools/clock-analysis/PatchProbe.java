// Print instructions/bytes at explicitly requested functions, without edits.
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
public class PatchProbe extends GhidraScript {
    public void run() throws Exception {
        for (String arg : getScriptArgs()) {
            Function f = getFunctionAt(toAddr(arg));
            if (f == null) throw new IllegalArgumentException("No function at " + arg);
            println("FUNCTION " + f.getName() + " " + f.getBody());
            for (Instruction ins : currentProgram.getListing().getInstructions(f.getBody(), true)) {
                StringBuilder bytes = new StringBuilder();
                for (byte b : ins.getBytes()) bytes.append(String.format("%02x", b));
                println(ins.getAddress() + " " + bytes + " " + ins);
            }
        }
        println("PATCH PROBE COMPLETE");
    }
}
