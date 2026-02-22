// PlayUnrealAutomation.Build.cs

using UnrealBuildTool;

public class PlayUnrealAutomation : ModuleRules
{
	public PlayUnrealAutomation(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"UMG",
			"SlateCore",
			"Slate",
			"InputCore",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Json",
			"JsonUtilities",
		});
	}
}
