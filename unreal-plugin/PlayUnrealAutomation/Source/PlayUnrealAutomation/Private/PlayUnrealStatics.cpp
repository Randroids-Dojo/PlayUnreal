// PlayUnrealStatics.cpp

#include "PlayUnrealStatics.h"
#include "Components/Widget.h"

// Store automation IDs in a static map keyed by widget pointer.
// This avoids modifying UWidget internals and works across UE versions.
static TMap<TWeakObjectPtr<const UWidget>, FString> AutomationIdMap;

void UPlayUnrealStatics::SetAutomationId(UWidget* Widget, const FString& Id)
{
	if (!Widget)
	{
		UE_LOG(LogTemp, Warning,
			TEXT("PlayUnreal: SetAutomationId called with null widget"));
		return;
	}

	if (Id.IsEmpty())
	{
		AutomationIdMap.Remove(Widget);
	}
	else
	{
		AutomationIdMap.Add(Widget, Id);
	}

	UE_LOG(LogTemp, Verbose,
		TEXT("PlayUnreal: SetAutomationId(%s) = '%s'"),
		*Widget->GetName(), *Id);
}

FString UPlayUnrealStatics::GetAutomationId(const UWidget* Widget)
{
	if (!Widget) return FString();

	const FString* Found = AutomationIdMap.Find(Widget);
	return Found ? *Found : FString();
}
