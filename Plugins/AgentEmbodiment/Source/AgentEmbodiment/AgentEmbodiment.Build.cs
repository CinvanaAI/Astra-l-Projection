using UnrealBuildTool;

public class AgentEmbodiment : ModuleRules
{
    public AgentEmbodiment(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "InputCore", "SlateCore" });
        PrivateDependencyModuleNames.AddRange(new[] { "Json", "RenderCore", "RHI", "Slate" });
    }
}
