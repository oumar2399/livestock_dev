import { useInfiniteQuery } from '@tanstack/react-query';
import { historyApi, TimelineParams } from '../api/history';

export function useAnimalTimeline(
  animalId: number | null,
  filters: Omit<TimelineParams, 'cursor'>,
) {
  return useInfiniteQuery({
    queryKey: ['timeline', animalId, filters],
    queryFn: ({ pageParam }) => historyApi.getTimeline(animalId as number, {
      ...filters,
      cursor: pageParam,
    }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: animalId !== null,
  });
}
