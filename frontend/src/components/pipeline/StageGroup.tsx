import { AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { StageItem } from "@/components/pipeline/StageItem";
import type { PipelineStage } from "@/types";

export function StageGroup({
  groupId,
  label,
  stages,
}: {
  groupId: string;
  label: string;
  stages: PipelineStage[];
}) {
  return (
    <AccordionItem value={groupId}>
      <AccordionTrigger className="py-2.5 text-xs tracking-[0.14em] text-text-muted">
        {label}
      </AccordionTrigger>
      <AccordionContent className="space-y-2">
        {stages.map((stage, index) => (
          <StageItem key={stage.key} stage={stage} index={index} />
        ))}
      </AccordionContent>
    </AccordionItem>
  );
}
