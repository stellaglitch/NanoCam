// For each address listed in a file (one hex address per line), prints the function's
// size and any callers that are outside the listed set. Used to measure how much code a
// feature owns.
// Headless usage: -postScript FuncSizes.java <path to address list>
//@category iPodCamera

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class FuncSizes extends GhidraScript {

	@Override
	protected void run() throws Exception {
		List<String> lines = Files.readAllLines(Paths.get(getScriptArgs()[0]));
		Set<Function> set = new HashSet<>();
		for (String l : lines) {
			l = l.trim();
			if (l.isEmpty()) continue;
			Address a = toAddr(Long.parseLong(l.replace("0x", ""), 16));
			Function f = getFunctionAt(a);
			if (f == null) f = getFunctionContaining(a);
			if (f != null) set.add(f);
			else println("NOFUNC " + l);
		}
		long total = 0, owned = 0;
		for (Function f : set) {
			long size = f.getBody().getNumAddresses();
			total += size;
			StringBuilder ext = new StringBuilder();
			for (Reference r : getReferencesTo(f.getEntryPoint())) {
				if (!r.getReferenceType().isCall()) continue;
				Function c = getFunctionContaining(r.getFromAddress());
				if (c == null || !set.contains(c)) ext.append(" ").append(r.getFromAddress());
			}
			if (ext.length() == 0) owned += size;
			println(String.format("SIZE %s %d%s", f.getEntryPoint(), size, ext.length() > 0 ? " EXTCALL" + ext : ""));
		}
		println(String.format("TOTAL %d functions, %d bytes; %d bytes with no outside callers", set.size(), total, owned));
	}
}
