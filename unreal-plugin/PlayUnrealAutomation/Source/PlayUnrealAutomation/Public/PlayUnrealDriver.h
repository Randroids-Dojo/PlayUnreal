// PlayUnrealDriver.h
//
// Central automation actor. Place one in your level and call its
// BlueprintCallable functions via the Remote Control API.
//
// All functions are designed to be called from external scripts
// (Python, curl) over HTTP through UE's Remote Control plugin.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PlayUnrealDriver.generated.h"

UCLASS(BlueprintType, Blueprintable)
class PLAYUNREALAUTOMATION_API APlayUnrealDriver : public AActor
{
	GENERATED_BODY()

public:
	APlayUnrealDriver();

	// -- Lifecycle ----------------------------------------------------------

	/** Health check. Returns version and session info as JSON. */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal")
	FString Ping() const;

	// -- UMG Widget Interaction --------------------------------------------

	/**
	 * Click a UMG widget by its Automation ID.
	 * The ID is set via UWidget::SetAutomationId() or
	 * UPlayUnrealStatics::SetAutomationId().
	 *
	 * @param Id  The automation ID string.
	 * @return    True if the widget was found and clicked.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|Input")
	bool ClickById(const FString& Id);

	/**
	 * Type text into the currently focused widget.
	 *
	 * @param Text  The text to type.
	 * @return      True if the text was sent successfully.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|Input")
	bool TypeText(const FString& Text);

	/**
	 * Simulate a key press.
	 *
	 * @param KeyChord  Key name (e.g., "Escape", "Enter", "SpaceBar").
	 * @return          True if the key was pressed.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|Input")
	bool PressKey(const FString& KeyChord);

	// -- Widget Queries ----------------------------------------------------

	/**
	 * Check if a widget with the given Automation ID exists.
	 *
	 * @param Id  The automation ID string.
	 * @return    True if found.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|Query")
	bool ElementExists(const FString& Id) const;

	/**
	 * Check if a widget is visible (exists and has Visible or SelfHitTestInvisible visibility).
	 *
	 * @param Id  The automation ID string.
	 * @return    True if visible.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|Query")
	bool IsVisible(const FString& Id) const;

	// -- Evidence ----------------------------------------------------------

	/**
	 * Take a screenshot and save to the given path.
	 * Path is relative to the project's Saved/ directory.
	 *
	 * @param Path  Output file path (e.g., "Screenshots/test.png").
	 * @return      Absolute path of the saved file, or empty on failure.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|Evidence")
	FString Screenshot(const FString& Path);

	// -- World Queries -----------------------------------------------------

	/**
	 * Find an actor by name in the current world.
	 *
	 * @param Name  Actor name or label.
	 * @return      Object path of the found actor, or empty if not found.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|World")
	FString FindActorByName(const FString& Name) const;

	/**
	 * Call a UFUNCTION on an arbitrary object by path.
	 *
	 * @param ObjectPath    UE object path.
	 * @param FunctionName  Name of the BlueprintCallable function.
	 * @param ParamsJSON    JSON string of parameters.
	 * @return              JSON string of the return value.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal|World")
	FString CallFunction(const FString& ObjectPath,
	                     const FString& FunctionName,
	                     const FString& ParamsJSON);

	// -- Timing ------------------------------------------------------------

	/**
	 * Wait for the given number of seconds (game time).
	 * Useful for sequencing actions from external scripts.
	 *
	 * @param Seconds  Duration to wait.
	 */
	UFUNCTION(BlueprintCallable, Category = "PlayUnreal")
	void WaitForSeconds(float Seconds);

protected:
	/** Plugin version string. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PlayUnreal")
	FString Version = TEXT("0.1.0");

	/** Session identifier (generated on construction). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PlayUnreal")
	FString SessionId;
};
