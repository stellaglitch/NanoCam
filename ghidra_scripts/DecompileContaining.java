// Decompiles the function that contains each given address (not just one starting there).
// Headless usage: -postScript DecompileContaining.java <hex address> ...
//@category iPodCamera

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class DecompileContaining extends GhidraScript {

	@Override
	protected void run() throws Exception {
		DecompInterface dec = new DecompInterface();
		dec.openProgram(currentProgram);
		for (String arg : getScriptArgs()) {
			Function f = getFunctionContaining(toAddr(Long.parseLong(arg.replace("0x", ""), 16)));
			if (f == null) {
				println("==== " + arg + ": no containing function");
				continue;
			}
			println("==== " + arg + " in " + f.getName() + " @ " + f.getEntryPoint());
			DecompileResults r = dec.decompileFunction(f, 60, monitor);
			println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "decompile failed: " + r.getErrorMessage());
		}
		dec.dispose();
	}
}
