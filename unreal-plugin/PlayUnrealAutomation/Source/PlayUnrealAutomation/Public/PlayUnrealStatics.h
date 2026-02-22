// PlayUnrealStatics.h
//
// Blueprint function library for PlayUnreal automation helpers.
// Use these to tag widgets with automation IDs and query widget state.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Components/Widget.h"
#include "PlayUnrealStatics.generated.h"

UCLASS()
class PLAYUNREALAUTOMATION_API UPlayUnrealStatics : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Set an automation ID on a UMG widget.
	 * This ID can be used by PlayUnreal scripts to find and interact
	 * with the widget via the Remote Control API.
	 *
	 * @param Widget  The UMG widget to tag.
	 * @param Id      The automation ID string (must be unique per screen).
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal",
	          meta = (DisplayName = "Set Automation ID"))
	static void SetAutomationId(UWidget* Widget, const FString& Id);

	/**
	 * Get the automation ID previously set on a widget.
	 *
	 * @param Widget  The widget to query.
	 * @return        The automation ID, or empty if not set.
	 */
	UFUNCTION(BlueprintCallable, BlueprintPure, Category = "PlayUnreal",
	          meta = (DisplayName = "Get Automation ID"))
	static FString GetAutomationId(const UWidget* Widget);
};
