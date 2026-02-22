// PlayUnrealDriver.cpp

#include "PlayUnrealDriver.h"

#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Widget.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/FileManager.h"
#include "JsonObjectConverter.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"
#include "Slate/SceneViewport.h"
#include "TimerManager.h"

APlayUnrealDriver::APlayUnrealDriver()
{
	PrimaryActorTick.bCanEverTick = false;
	SessionId = FGuid::NewGuid().ToString();
}

// ---------------------------------------------------------------------------
// Ping
// ---------------------------------------------------------------------------

FString APlayUnrealDriver::Ping() const
{
	return FString::Printf(
		TEXT("{\"version\":\"%s\",\"session\":\"%s\"}"),
		*Version, *SessionId);
}

// ---------------------------------------------------------------------------
// UMG Widget Interaction (stubs — requires Automation Driver wiring)
// ---------------------------------------------------------------------------

static UWidget* FindWidgetById(const UWorld* World, const FString& Id)
{
	if (!World) return nullptr;

	// Iterate all player controllers and their HUD widgets
	for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
	{
		APlayerController* PC = It->Get();
		if (!PC) continue;

		// Check all widgets owned by this player
		TArray<UUserWidget*> Widgets;
		UWidgetTree::ForEachWidget(PC, [&](UWidget* Widget)
		{
			// UWidget doesn't have GetAutomationId in all UE versions.
			// Check the widget's name as a fallback identifier.
			if (Widget && Widget->GetName() == Id)
			{
				// Found
			}
		});
	}

	// Stub: full implementation requires Automation Driver integration
	return nullptr;
}

bool APlayUnrealDriver::ClickById(const FString& Id)
{
	UE_LOG(LogTemp, Log, TEXT("PlayUnreal: ClickById(%s) — stub"), *Id);
	// TODO: Wire to Automation Driver By::Id locator
	return false;
}

bool APlayUnrealDriver::TypeText(const FString& Text)
{
	UE_LOG(LogTemp, Log, TEXT("PlayUnreal: TypeText(%s) — stub"), *Text);
	// TODO: Wire to Automation Driver input sequence
	return false;
}

bool APlayUnrealDriver::PressKey(const FString& KeyChord)
{
	UE_LOG(LogTemp, Log, TEXT("PlayUnreal: PressKey(%s) — stub"), *KeyChord);
	// TODO: Wire to FSlateApplication::ProcessKeyDownEvent
	return false;
}

bool APlayUnrealDriver::ElementExists(const FString& Id) const
{
	UE_LOG(LogTemp, Log, TEXT("PlayUnreal: ElementExists(%s) — stub"), *Id);
	return false;
}

bool APlayUnrealDriver::IsVisible(const FString& Id) const
{
	UE_LOG(LogTemp, Log, TEXT("PlayUnreal: IsVisible(%s) — stub"), *Id);
	return false;
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------

FString APlayUnrealDriver::Screenshot(const FString& Path)
{
	FString FullPath = FPaths::Combine(FPaths::ProjectSavedDir(), Path);
	FPaths::MakeStandardFilename(FullPath);

	// Ensure directory exists
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(FullPath), true);

	// Request a screenshot from the engine
	FScreenshotRequest::RequestScreenshot(FullPath, false, false);

	UE_LOG(LogTemp, Log, TEXT("PlayUnreal: Screenshot requested -> %s"), *FullPath);
	return FullPath;
}

// ---------------------------------------------------------------------------
// World Queries
// ---------------------------------------------------------------------------

FString APlayUnrealDriver::FindActorByName(const FString& Name) const
{
	UWorld* World = GetWorld();
	if (!World) return FString();

	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (Actor && (Actor->GetName() == Name || Actor->GetActorLabel() == Name))
		{
			return Actor->GetPathName();
		}
	}

	return FString();
}

FString APlayUnrealDriver::CallFunction(const FString& ObjectPath,
                                         const FString& FunctionName,
                                         const FString& ParamsJSON)
{
	UE_LOG(LogTemp, Log,
		TEXT("PlayUnreal: CallFunction(%s, %s) — delegating to Remote Control"),
		*ObjectPath, *FunctionName);

	// This function is a convenience wrapper. In practice, external scripts
	// call functions directly via PUT /remote/object/call. This stub exists
	// so the function can be called through the driver actor if needed.
	return TEXT("{\"status\":\"stub\"}");
}

// ---------------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------------

void APlayUnrealDriver::WaitForSeconds(float Seconds)
{
	// Note: This blocks the game thread briefly. For non-blocking waits,
	// use a timer. This is acceptable for automation scripts that are
	// orchestrating from an external process.
	if (Seconds > 0.0f && Seconds < 30.0f)
	{
		FTimerHandle Handle;
		GetWorld()->GetTimerManager().SetTimer(Handle, Seconds, false);
	}
}
