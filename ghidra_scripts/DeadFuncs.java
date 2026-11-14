// Lists functions that nothing references (no calls, no data pointers), largest first.
// Candidates for reuse as code space; double-check each with a raw byte scan.
// Headless usage: -postScript DeadFuncs.java [min size, default 256]
//@category NanoCam

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.util.ArrayList;
import java.util.List;

public class DeadFuncs extends GhidraScript {

	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		long min = args.length > 0 ? Long.parseLong(args[0]) : 256;
		List<long[]> found = new ArrayList<>();
		for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
			Address e = f.getEntryPoint();
			if (getReferencesTo(e).length > 0) continue;
			if (getReferencesTo(e.add(1)).length > 0) continue;
			long size = f.getBody().getNumAddresses();
			if (size >= min) found.add(new long[] { e.getOffset(), size });
		}
		found.sort((a, b) -> Long.compare(b[1], a[1]));
		for (long[] r : found) {
			Function f = getFunctionAt(toAddr(r[0]));
			println(String.format("DEAD %08x %6d %s", r[0], r[1], f.getName()));
		}
	}
}
