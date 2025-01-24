"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import {
  DiscordIcon,
  SlackIcon,
  SendTestMessageIcon,
  SolarTrashBinTrashBold
} from "@/components/Icons";
import { cn } from "@/lib/utils";
import {
  getIntegrationDetails,
  getIntegrationChannels,
  saveIntegrationChannels,
  sendIntegrationTestMessage,
  deleteIntegration
} from "@/app/actions";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Trash2, Check } from "lucide-react";
import LoadingSkeleton from "@/components/Content/LoadingSkeleton";
import { Input } from "@/components/ui/input";
import { ConnectedIntegrationIcon } from "@/components/Icons";

const IntegrationContent = ({ type, customGuru, error }) => {
  const [integrationData, setIntegrationData] = useState(null);
  const [channels, setChannels] = useState([]);
  const [internalError, setInternalError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [channelsLoading, setChannelsLoading] = useState(true);
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const integrationConfig = {
    slack: {
      name: "Slack",
      description:
        "By connecting your account, you can easily share all your posts and invite your friends.",
      iconSize: "w-5 h-5",
      url: `https://slack.com/oauth/v2/authorize?client_id=8327841447732.8318709976774&scope=channels:history,channels:join,channels:read,chat:write,groups:history,im:history,groups:read,mpim:read,im:read&user_scope=channels:history,chat:write,channels:read,groups:read,groups:history,im:history`,
      icon: SlackIcon
    },
    discord: {
      name: "Discord",
      description:
        "Connect your Discord account to share content and interact with your community.",
      bgColor: "bg-[#5865F2]",
      iconSize: "w-5 h-5",
      url: `https://discord.com/oauth2/authorize?client_id=1331218460075757649&permissions=8&response_type=code&redirect_uri=https%3A%2F%2Fe306-34-32-48-186.ngrok-free.app%2FOAuth&integration_type=0&scope=identify+bot`,
      icon: DiscordIcon
    }
  };
  const config = integrationConfig[type];

  const integrationUrl = config.url;

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch integration details
        const data = await getIntegrationDetails(
          customGuru,
          type.toUpperCase()
        );

        // Case 1: 202 Accepted - Show create content
        if (data?.status === 202) {
          setIntegrationData(data);
          setInternalError(null);
          return;
        }

        // Case 2: Error response
        if (data?.error) {
          throw new Error(data.message || "Failed to fetch integration data");
        }

        // Case 3: Successful response with integration data
        setIntegrationData(data);
        setInternalError(null);

        // Fetch channels separately
        fetchChannels();
      } catch (err) {
        setInternalError(err.message);
        setIntegrationData(null);
      } finally {
        setLoading(false);
      }
    };

    const fetchChannels = async () => {
      try {
        const channelsData = await getIntegrationChannels(
          customGuru,
          type.toUpperCase()
        );
        if (channelsData?.error) {
          console.error("Failed to fetch channels:", channelsData.message);
        } else {
          setChannels(channelsData?.channels || []);
        }
      } catch (err) {
        console.error("Failed to fetch channels:", err);
      } finally {
        setChannelsLoading(false);
      }
    };

    fetchData();
  }, [customGuru, type]);

  const Icon = config.icon;
  const name = config.name;

  if (loading) {
    return (
      <div className="w-full">
        <h2 className="text-[#191919] font-inter text-[20px] font-medium p-6">
          {name} Bot
        </h2>
        <div className="h-[1px] bg-neutral-200" />
        <div className="p-6">
          <LoadingSkeleton count={2} width={400} />
        </div>
      </div>
    );
  }

  if (internalError) {
    return (
      <div className="w-full">
        <h2 className="text-[#191919] font-inter text-[20px] font-medium p-6">
          {name} Bot
        </h2>
        <div className="h-[1px] bg-neutral-200" />
        <div className="p-6 text-red-500">{internalError}</div>
      </div>
    );
  }

  if (integrationData && !integrationData?.encoded_guru_slug) {
    return (
      <div className="w-full">
        <h2 className="text-[#191919] font-inter text-[20px] font-medium p-6">
          {name} Bot
        </h2>
        <div className="h-[1px] bg-neutral-200" />
        <div className="flex flex-col gap-6 p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  "w-10 h-10 rounded-full flex items-center justify-center border border-neutral-200"
                )}>
                <Icon className={cn(config.iconSize, "text-white")} />
              </div>
              <div>
                <h3 className="font-medium">{name}</h3>
                <p className="text-sm text-muted-foreground">
                  By connecting your account, you can easily share all your
                  posts and invite your friends.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button
                variant="destructive"
                disabled={isDisconnecting}
                onClick={async () => {
                  setIsDisconnecting(true);
                  try {
                    const response = await deleteIntegration(
                      customGuru,
                      type.toUpperCase()
                    );
                    if (!response?.error) {
                      setIntegrationData(response);
                      setInternalError(null);
                    } else {
                      setInternalError(
                        response.message || "Failed to disconnect integration"
                      );
                    }
                  } catch (error) {
                    setInternalError(error.message);
                  } finally {
                    setIsDisconnecting(false);
                  }
                }}
                className="bg-white hover:bg-white text-red-500 hover:text-red-600 border border-neutral-200 rounded-full gap-2">
                <Trash2 className="h-4 w-4" />
                {isDisconnecting ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
                    Disconnecting...
                  </div>
                ) : (
                  "Disconnect"
                )}
              </Button>
              <Button
                variant="outline"
                className="bg-white hover:bg-white text-[#232323] border border-neutral-200 rounded-full gap-2">
                <ConnectedIntegrationIcon />
                Connected to {integrationData.workspace_name}
              </Button>
            </div>
          </div>
          <div className="">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium">Channels</h3>
              <Button
                disabled={!hasChanges || isSaving}
                onClick={async () => {
                  setIsSaving(true);
                  try {
                    const response = await saveIntegrationChannels(
                      customGuru,
                      type.toUpperCase(),
                      channels
                    );
                    if (!response?.error) {
                      setHasChanges(false);
                    }
                  } catch (error) {
                    console.error("Failed to save channels:", error);
                  } finally {
                    setIsSaving(false);
                  }
                }}>
                {isSaving ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Saving...
                  </div>
                ) : (
                  "Save Changes"
                )}
              </Button>
            </div>
            <p className="text-[#6D6D6D] font-inter text-[14px] font-normal mb-4">
              Select the channels you want, click <strong>Save</strong>, then
              test the connection for each channel using{" "}
              <strong>Send test message</strong>, and call the bot with{" "}
              <strong>@gurubase</strong>.
            </p>
            {/* Allowed Channels */}
            {channelsLoading ? (
              <div className="space-y-4">
                <LoadingSkeleton count={3} width={400} />
              </div>
            ) : (
              <>
                <div className="space-y-4 mb-6">
                  {channels
                    .filter((c) => c.allowed)
                    .map((channel) => (
                      <div key={channel.id} className="flex items-center gap-3">
                        <div className="relative w-full md:w-[300px]">
                          <span className="absolute left-3 top-2 text-xs font-normal text-gray-500">
                            Channel
                          </span>
                          <Input
                            readOnly
                            className="bg-gray-50 pt-8 pb-2"
                            value={channel.name}
                          />
                        </div>
                        <Button
                          variant="outline"
                          className="flex h-[36px] px-4 justify-center items-center gap-2 rounded-full border border-[#E2E2E2] bg-white hover:bg-white text-[#191919] font-inter text-[14px] font-medium"
                          onClick={async () => {
                            try {
                              const response = await sendIntegrationTestMessage(
                                integrationData.id,
                                channel.id
                              );
                              if (response?.error) {
                                console.error(
                                  "Failed to send test message:",
                                  response.message
                                );
                              }
                            } catch (error) {
                              console.error(
                                "Error sending test message:",
                                error
                              );
                            }
                          }}>
                          <SendTestMessageIcon />
                          Send Test Message
                        </Button>
                        <div className="flex items-center">
                          <Button
                            variant="trashIcon"
                            size="noSpace"
                            onClick={() => {
                              setChannels(
                                channels.map((c) =>
                                  c.id === channel.id
                                    ? { ...c, allowed: false }
                                    : c
                                )
                              );
                              setHasChanges(true);
                            }}>
                            <SolarTrashBinTrashBold className="h-6 w-6" />
                          </Button>
                        </div>
                      </div>
                    ))}
                </div>
                {/* Add New Channel */}
                {channels.filter((c) => !c.allowed).length > 0 && (
                  <div className="mt-6">
                    <div className="flex items-center gap-3">
                      <div className="relative w-full md:w-[300px]">
                        <Select
                          key={channels.filter((c) => !c.allowed).length}
                          value=""
                          onValueChange={(value) => {
                            setChannels(
                              channels.map((c) =>
                                c.id === value ? { ...c, allowed: true } : c
                              )
                            );
                            setHasChanges(true);
                          }}>
                          <SelectTrigger
                            className="bg-white border border-[#E2E2E2] text-[14px] rounded-lg h-[48px] px-3 flex items-center gap-2 self-stretch"
                            arrow={false}>
                            <div className="flex flex-col items-start">
                              <span className="text-[12px] text-gray-500">
                                Channel
                              </span>
                              <SelectValue placeholder="Select a channel..." />
                            </div>
                            <svg
                              className="h-4 w-4 opacity-50 ml-auto"
                              fill="none"
                              viewBox="0 0 24 24"
                              xmlns="http://www.w3.org/2000/svg">
                              <path
                                d="M7 10L12 15L17 10"
                                stroke="currentColor"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="2"
                              />
                            </svg>
                          </SelectTrigger>
                          <SelectContent className="bg-white border border-[#E5E7EB] text-[14px] rounded-lg shadow-lg">
                            {channels
                              .filter((c) => !c.allowed)
                              .map((channel) => (
                                <SelectItem
                                  key={channel.id}
                                  value={channel.id}
                                  className="px-4 py-2 hover:bg-[#F3F4F6] cursor-pointer">
                                  {channel.name}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Default case: Show create content (204 or no integration)
  return (
    <div className="w-full">
      <h2 className="text-[#191919] font-inter text-[20px] font-medium p-6">
        {name} Bot
      </h2>
      <div className="h-[1px] bg-neutral-200" />
      <div className="flex items-center justify-between p-6">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "w-10 h-10 rounded-full flex items-center justify-center border border-neutral-200"
            )}>
            <Icon className={cn(config.iconSize, "text-white")} />
          </div>
          <div>
            <h3 className="font-medium">{config.name}</h3>
            <p className="text-sm text-muted-foreground">
              {config.description}
            </p>
          </div>
        </div>
        <Button
          variant="default"
          className="bg-[#1a1a1a] text-white hover:bg-[#2a2a2a]"
          onClick={() =>
            window.open(
              `${integrationUrl}&state=${JSON.stringify({
                type: type,
                guru_type: customGuru,
                encoded_guru_slug: integrationData?.encoded_guru_slug
              })}`,
              "_blank"
            )
          }>
          Connect
        </Button>
      </div>
      {error && (
        <div className="text-red-500 bg-red-50 p-4 rounded-md">
          There was an error during the integration process. Please try again or
          contact support if the issue persists.
        </div>
      )}
    </div>
  );
};

export default IntegrationContent;
