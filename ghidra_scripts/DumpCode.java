// Prints instructions starting at an address, with the values of any literal-pool loads.
// Headless usage: -postScript DumpCode.java <hex address> <instruction count>
//@category NanoCam

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class DumpCode extends GhidraScript {

	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		Address addr = toAddr(Long.parseLong(args[0].replace("0x", ""), 16));
		int count = args.length > 1 ? Integer.parseInt(args[1]) : 60;

		Instruction insn = getInstructionAt(addr);
		if (insn == null) {
			disassemble(addr);
			insn = getInstructionAt(addr);
		}
		for (int i = 0; i < count && insn != null; i++) {
			StringBuilder line = new StringBuilder(String.format("%s  %s", insn.getAddress(), insn));
			for (Reference ref : insn.getReferencesFrom()) {
				if (ref.getReferenceType().isRead()) {
					try {
						line.append(String.format("    ; =0x%08x", getInt(ref.getToAddress())));
					}
					catch (Exception e) {
						// Not readable.
					}
				}
			}
			println(line.toString());
			insn = insn.getNext();
		}
	}
}
