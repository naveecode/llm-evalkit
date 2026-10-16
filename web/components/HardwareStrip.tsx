import { gibibytes, stamp } from "@/lib/format";
import type { Hardware } from "@/lib/types";

export function HardwareStrip({ hardware }: { hardware: Hardware }) {
  const cpuLibrary = hardware.ggmlLibraries.find((name) => name.includes("libggml-cpu"));
  return (
    <section className="grid gap-4 rounded-lg border border-line bg-panel p-4 sm:grid-cols-2">
      <Fact
        label="CPU"
        value={hardware.cpuModel}
        detail={`family ${hardware.cpuFamily} · model ${hardware.cpuModelId} · stepping ${hardware.cpuStepping} · ${hardware.logicalCpus} logical CPUs`}
      />
      <Fact
        label="Memory"
        value={gibibytes(hardware.memoryTotalBytes)}
        detail={`${gibibytes(hardware.memoryAvailableBytes)} available when this file was written`}
      />
      <Fact
        label="Server"
        value={`Ollama ${hardware.backendVersion}`}
        detail={`${hardware.runner}${cpuLibrary ? ` · ${cpuLibrary}` : ""}`}
      />
      <Fact label="Recorded" value={stamp(hardware.collectedAt)} detail={hardware.kernel} />
      {hardware.acceleratorLibraries.length > 0 ? (
        <p className="text-sm text-muted sm:col-span-2">
          Accelerator libraries: {hardware.acceleratorLibraries.join(", ")}
        </p>
      ) : null}
    </section>
  );
}

function Fact({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className="mt-1 text-sm text-paper">{value}</p>
      <p className="mt-1 text-xs leading-relaxed text-muted">{detail}</p>
    </div>
  );
}
