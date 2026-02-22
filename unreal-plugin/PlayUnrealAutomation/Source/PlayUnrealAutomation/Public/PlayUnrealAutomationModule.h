// PlayUnrealAutomationModule.h

#pragma once

#include "Modules/ModuleManager.h"

class FPlayUnrealAutomationModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};
